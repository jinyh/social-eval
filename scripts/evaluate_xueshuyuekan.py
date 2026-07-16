#!/usr/bin/env python3
"""学术月刊 E1 评价脚本（自包含）

对 raw/xueshuyuekan/ 下的 149 篇论文执行完整 E1 评价流程：
  预检（项目口径判断）→ Round 1（4 模型 × 6 维度）→ Round 2（交叉评审）

不依赖已归档的 run_convergence_test.py / run_cross_review.py。

用法：
    .venv/bin/python scripts/evaluate_xueshuyuekan.py \
        --input-dir raw/xueshuyuekan/ \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --output-dir results/xueshuyuekan \
        --concurrency 5

    # 只跑特定论文 ID
    .venv/bin/python scripts/evaluate_xueshuyuekan.py \
        --input-dir raw/xueshuyuekan/ \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --output-dir results/xueshuyuekan \
        --concurrency 5 \
        --paper-ids 1,2,3
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import (
    build_prompt,
    build_precheck_prompt,
    build_signal_check_prompt,
    _paper_content,
    _reference_content,
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework as load_validated_framework
from src.knowledge.schemas import Framework
from src.reporting.scoring import calculate_weighted_total


# ── 常量 ──

MODELS = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
A_GROUP = ['glm-5.1', 'qwen3.6-plus']   # 宽松组
B_GROUP = ['deepseek-v4-pro', 'kimi-k2.6']  # 严格组


# ── 工具函数 ──

def setup_logging(output_dir: Path) -> logging.Logger:
    """配置日志"""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def load_framework(framework_path: str) -> Framework:
    """加载并校验框架配置。"""
    return load_validated_framework(framework_path)


def generate_paper_list(input_dir: str) -> list[dict]:
    """从目录生成论文列表"""
    md_files = sorted(Path(input_dir).glob("*.md"))
    papers = []
    for idx, fp in enumerate(md_files, start=1):
        stem = fp.stem
        parts = stem.split('_')
        ncpssd_id = parts[0]

        # 找 '学术月刊' 的位置
        journal_idx = None
        for i, p in enumerate(parts):
            if p == '学术月刊':
                journal_idx = i
                break

        if journal_idx and journal_idx >= 2:
            author = '_'.join(parts[1:journal_idx - 1]) if journal_idx > 2 else parts[1]
            year_str = parts[journal_idx - 1]
            title = '_'.join(parts[journal_idx + 1:])
        else:
            author = parts[1] if len(parts) > 1 else ''
            year_str = parts[2] if len(parts) > 2 else ''
            title = '_'.join(parts[4:]) if len(parts) > 4 else stem

        papers.append({
            'id': idx,
            'path': str(fp),
            'filename': fp.name,
            'ncpssd_id': ncpssd_id,
            'author': author,
            'year': int(year_str) if year_str.isdigit() else 0,
            'title': title,
        })
    return papers


def aggregate_scores(model_scores: dict[str, float], mode: str = "both") -> dict:
    """聚合多模型分数"""
    scores = list(model_scores.values())
    result = {"model_scores": model_scores}

    if mode in ("mean", "both"):
        result["mean"] = round(statistics.mean(scores), 1) if scores else 0.0
        result["std"] = round(statistics.stdev(scores), 1) if len(scores) > 1 else 0.0

    if mode in ("strictest", "both"):
        min_score = min(scores) if scores else 0.0
        result["strictest"] = min_score
        for model, score in model_scores.items():
            if score == min_score:
                result["strictest_model"] = model
                break

    return result


def confidence_from_std(std: float) -> str:
    """根据标准差确定置信度"""
    if std <= 5.0:
        return "high"
    elif std <= 8.0:
        return "medium"
    elif std <= 12.0:
        return "low"
    else:
        return "critical"


# ── Provider 调用 ──

async def call_provider(provider, prompt: str) -> tuple[dict | None, str | None, float]:
    """调用单个 provider"""
    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
        elapsed = time.time() - start
        return raw, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return None, str(e), elapsed


# ── 预检 ──

async def run_precheck(providers, framework, paper) -> dict:
    """运行项目口径预检"""
    if not framework.precheck:
        return {"skipped": True, "reason": "框架未配置 precheck"}

    prompt = build_precheck_prompt(framework, paper)
    results = await asyncio.gather(
        *[call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    precheck_results = {}
    for (raw, error, elapsed), provider in zip(results, providers):
        if error:
            precheck_results[provider.model_name] = {"error": error, "elapsed": elapsed}
        else:
            precheck_results[provider.model_name] = {
                "result": raw,
                "elapsed": elapsed,
            }
    return precheck_results


# ── Round 1：六维评分 ──

async def evaluate_single_dimension(
    providers, dimension, paper, aggregation_mode: str = "both"
) -> dict:
    """并发调用所有 provider 评估单个维度"""
    prompt = build_prompt(dimension, paper)

    results = await asyncio.gather(
        *[call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    scores = {}
    raw_outputs = {}
    errors = {}
    elapsed_times = {}

    for (raw, error, elapsed), provider in zip(results, providers):
        elapsed_times[provider.model_name] = elapsed
        if error:
            errors[provider.model_name] = error
            continue
        raw_outputs[provider.model_name] = raw
        if isinstance(raw, dict):
            score = raw.get("score")
        else:
            errors[provider.model_name] = f"非 dict 输出: {type(raw).__name__}"
            continue
        if score is not None:
            scores[provider.model_name] = int(score)

    aggregated = aggregate_scores(scores, aggregation_mode)

    std = aggregated.get("std", 0.0)
    confidence = confidence_from_std(std)

    result = {
        "dimension": dimension.key,
        "name_zh": dimension.name_zh,
        "confidence": confidence,
        "raw_outputs": raw_outputs,
        "errors": errors,
        "elapsed_times": elapsed_times,
    }
    result.update(aggregated)
    return result


async def run_round1(
    paper_path: str,
    framework: Framework,
    providers: list,
    framework_path: str,
) -> dict:
    """执行单篇论文的 Round 1（预检 + 六维评分 + 信号校验）"""
    paper = process_file(paper_path)

    result = {
        "paper": paper_path,
        "framework": framework_path,
        "models": [p.model_name for p in providers],
        "timestamp": datetime.now().isoformat(),
    }

    # 1. 预检
    result["precheck"] = await run_precheck(providers, framework, paper)

    # 2. 六维评分（维度级并发，每维度内部 4 模型并发）
    dim_semaphore = asyncio.Semaphore(6)

    async def eval_dim(dim):
        async with dim_semaphore:
            return await evaluate_single_dimension(providers, dim, paper)

    dim_results = await asyncio.gather(
        *[eval_dim(dim) for dim in framework.dimensions]
    )

    dimensions = {}
    for dim, dim_result in zip(framework.dimensions, dim_results):
        dimensions[dim.key] = dim_result

    result["dimensions"] = dimensions

    # 3. 自主知识体系信号校验
    try:
        signal_prompt = build_signal_check_prompt(framework, paper)
        signal_results = await asyncio.gather(
            *[call_provider(p, signal_prompt) for p in providers],
            return_exceptions=False,
        )
        signals = {}
        for (raw, error, elapsed), provider in zip(signal_results, providers):
            if error:
                signals[provider.model_name] = {"error": error}
            else:
                signals[provider.model_name] = raw
        result["autonomous_knowledge_signals"] = signals
    except Exception as e:
        result["autonomous_knowledge_signals"] = {"error": str(e)}

    # 4. 计算总体统计
    result["overall"] = compute_overall(dimensions, framework)

    return result


def compute_overall(dimensions: dict, framework: Framework) -> dict:
    """计算总体统计指标"""
    # 收集各维度的 mean 和 std
    dim_means = {}
    dim_stds = {}
    max_std = 0.0
    std_over_8 = 0

    for dim_key, dim_data in dimensions.items():
        mean = dim_data.get("mean", 0)
        std = dim_data.get("std", 0)
        dim_means[dim_key] = mean
        dim_stds[dim_key] = std
        if std > max_std:
            max_std = std
        if std > 8:
            std_over_8 += 1

    # 加权总分（使用框架的 scoring_protocol）
    scoring_protocol = None
    dimension_weights = None
    if hasattr(framework, 'raw_config') and framework.raw_config:
        scoring_protocol = framework.raw_config.get("scoring_protocol")
    if not scoring_protocol:
        dimension_weights = {d.key: d.weight for d in framework.dimensions}

    final_score_mean = calculate_weighted_total(
        dim_means, scoring_protocol=scoring_protocol, dimension_weights=dimension_weights
    )

    # strictest 总分
    strictest_scores = {}
    for dim_key, dim_data in dimensions.items():
        strictest_scores[dim_key] = dim_data.get("strictest", dim_data.get("mean", 0))
    final_score_strictest = calculate_weighted_total(
        strictest_scores, scoring_protocol=scoring_protocol, dimension_weights=dimension_weights
    )

    return {
        "aggregation_mean": {"final_score": final_score_mean},
        "aggregation_strictest": {"final_score": final_score_strictest},
        "max_std": round(max_std, 1),
        "dimensions_std_over_8": std_over_8,
        "dimension_means": dim_means,
        "dimension_stds": dim_stds,
        "confidence": confidence_from_std(max_std),
    }


# ── Round 2：交叉评审 ──

def build_cross_review_prompt(
    dimension_name: str,
    dimension_key: str,
    self_output: dict,
    other_group_outputs: list[dict],
    paper,
) -> str:
    """构建交叉评审 prompt"""
    self_score = self_output.get('score', 0)
    self_band = self_output.get('band', '')
    self_core_judgment = self_output.get('core_judgment', '')
    self_score_rationale = self_output.get('score_rationale', '')
    self_strengths = self_output.get('strengths', [])
    self_weaknesses = self_output.get('weaknesses', [])
    self_evidence_quotes = self_output.get('evidence_quotes', [])

    self_strengths_str = '\n'.join(f'  - {s}' for s in self_strengths) if self_strengths else '  （无）'
    self_weaknesses_str = '\n'.join(f'  - {w}' for w in self_weaknesses) if self_weaknesses else '  （无）'
    self_evidence_str = '\n'.join(f'  - {e}' for e in self_evidence_quotes) if self_evidence_quotes else '  （无）'

    other_reviews = []
    for i, other_output in enumerate(other_group_outputs, 1):
        o_score = other_output.get('score', 0)
        o_band = other_output.get('band', '')
        o_core = other_output.get('core_judgment', '')
        o_rationale = other_output.get('score_rationale', '')
        o_strengths = other_output.get('strengths', [])
        o_weaknesses = other_output.get('weaknesses', [])
        o_evidence = other_output.get('evidence_quotes', [])

        o_strengths_str = '\n'.join(f'  - {s}' for s in o_strengths) if o_strengths else '  （无）'
        o_weaknesses_str = '\n'.join(f'  - {w}' for w in o_weaknesses) if o_weaknesses else '  （无）'
        o_evidence_str = '\n'.join(f'  - {e}' for e in o_evidence) if o_evidence else '  （无）'

        review = (
            f"【评审专家 {chr(64 + i)}】\n"
            f"评分：{o_score}\n"
            f"评分档位：{o_band}\n"
            f"核心判断：{o_core}\n"
            f"评分理由：{o_rationale}\n"
            f"优点：\n{o_strengths_str}\n"
            f"缺点：\n{o_weaknesses_str}\n"
            f"证据引用：\n{o_evidence_str}"
        )
        other_reviews.append(review)

    other_reviews_str = '\n\n'.join(other_reviews)

    prompt = (
        f"你是一位法学论文评审专家。你之前对这篇论文的【{dimension_name}】维度给出了以下评价：\n\n"
        f"【你的第一轮评价】\n"
        f"评分：{self_score}\n"
        f"评分档位：{self_band}\n"
        f"核心判断：{self_core_judgment}\n"
        f"评分理由：{self_score_rationale}\n"
        f"优点：\n{self_strengths_str}\n"
        f"缺点：\n{self_weaknesses_str}\n"
        f"证据引用：\n{self_evidence_str}\n\n"
        f"---\n\n"
        f"现在，另一组评审专家对同一篇论文的同一维度给出了不同的评价：\n\n"
        f"{other_reviews_str}\n\n"
        f"---\n\n"
        f"请你重新阅读论文原文，结合其他专家的意见，重新审视你的评价：\n\n"
        f"论文正文：\n{_paper_content(paper)}\n\n"
        f"---\n"
        f"参考文献列表：\n{_reference_content(paper)}\n\n"
        f"---\n\n"
        f"请仔细思考以下问题：\n"
        f"1. 其他专家的意见中是否有你之前忽略的合理观点？\n"
        f"2. 重新阅读论文后，你是否发现了之前遗漏的证据或论证？\n"
        f"3. 你是否需要修改你的评分？\n\n"
        f"请输出 JSON：\n"
        f"{{\n"
        f'  "original_score": {self_score},\n'
        f'  "revised_score": <你修改后的评分（如果不修改则与原分相同）>,\n'
        f'  "score_changed": true/false,\n'
        f'  "change_direction": "up" | "down" | "unchanged",\n'
        f'  "change_magnitude": <分数变化的绝对值>,\n'
        f'  "revised_band": "excellent" | "good" | "marginal" | "unacceptable",\n'
        f'  "revised_core_judgment": "重新审视后的核心判断（≤80字）",\n'
        f'  "revision_rationale": "修改理由（≤200字）",\n'
        f'  "accepted_points": ["从对方意见中接受的观点"],\n'
        f'  "rejected_points": ["从对方意见中拒绝的观点及理由"],\n'
        f'  "new_evidence_found": ["重新阅读论文后发现的新证据"],\n'
        f'  "confidence": "high" | "medium" | "low"\n'
        f"}}"
    )
    return prompt


async def run_round2(
    paper_path: str,
    round1_result: dict,
    framework: Framework,
    providers: dict[str, object],
    r2_semaphore: asyncio.Semaphore,
    logger: logging.Logger,
    paper_id: int,
) -> dict:
    """执行单篇论文的 Round 2 交叉评审"""
    paper = process_file(paper_path)
    dimensions_data = round1_result.get("dimensions", {})

    round2_result = {
        "paper": paper_path,
        "framework": round1_result.get("framework", ""),
        "models": round1_result.get("models", []),
        "dimensions": {},
        "overall": {},
    }

    for dim_key, dim_data in dimensions_data.items():
        if dim_key == "autonomous_knowledge_signals":
            continue

        dim_config = next(
            (d for d in framework.dimensions if d.key == dim_key), None
        )
        if not dim_config:
            continue

        raw_outputs = dim_data.get("raw_outputs", {})

        # 对每个模型执行交叉评审
        round2_scores = {}
        round2_raw_outputs = {}
        changes = {}

        tasks = []
        model_names_for_tasks = []

        for model_name in A_GROUP + B_GROUP:
            if model_name not in raw_outputs:
                continue

            provider = providers.get(model_name)
            if not provider:
                continue

            self_output = raw_outputs[model_name]
            other_group = B_GROUP if model_name in A_GROUP else A_GROUP
            other_outputs = [
                raw_outputs[m] for m in other_group if m in raw_outputs
            ]

            if not other_outputs:
                continue

            prompt = build_cross_review_prompt(
                dim_config.name_zh, dim_key, self_output, other_outputs, paper
            )

            async def call_with_sem(p, pr):
                async with r2_semaphore:
                    return await call_provider(p, pr)

            tasks.append(call_with_sem(provider, prompt))
            model_names_for_tasks.append(model_name)

        if not tasks:
            continue

        results = await asyncio.gather(*tasks, return_exceptions=False)

        for model_name, (raw, error, elapsed) in zip(model_names_for_tasks, results):
            r1_score = dim_data.get("model_scores", {}).get(model_name)

            if error:
                logger.warning(
                    f"[R2] id={paper_id} {dim_key} {model_name} → 失败: {error}"
                )
                continue

            if raw and isinstance(raw, dict):
                round2_raw_outputs[model_name] = raw
                revised_score = raw.get("revised_score")
                if revised_score is not None:
                    round2_scores[model_name] = int(revised_score)
                    changes[model_name] = {
                        "original": r1_score,
                        "revised": int(revised_score),
                        "changed": raw.get("score_changed", r1_score != revised_score),
                        "direction": raw.get("change_direction", "unchanged"),
                        "magnitude": raw.get("change_magnitude", 0),
                        "confidence": raw.get("confidence", "medium"),
                    }

        if round2_scores:
            r1_scores = {k: v for k, v in dim_data.get("model_scores", {}).items()}
            r2_mean = round(statistics.mean(round2_scores.values()), 1)
            r2_std = round(statistics.stdev(round2_scores.values()), 1) if len(round2_scores) > 1 else 0.0
            r1_mean = dim_data.get("mean", 0)
            r1_std = dim_data.get("std", 0)

            round2_result["dimensions"][dim_key] = {
                "round1_scores": r1_scores,
                "round2_scores": round2_scores,
                "changes": changes,
                "round1_mean": r1_mean,
                "round2_mean": r2_mean,
                "round1_std": r1_std,
                "round2_std": r2_std,
                "convergence_improvement": round(r1_std - r2_std, 1),
                "round2_raw_outputs": round2_raw_outputs,
            }

    # 计算 Round 2 总体统计
    if round2_result["dimensions"]:
        all_r2_means = [d["round2_mean"] for d in round2_result["dimensions"].values()]
        all_r2_stds = [d["round2_std"] for d in round2_result["dimensions"].values()]
        all_r1_stds = [d["round1_std"] for d in round2_result["dimensions"].values()]

        round2_result["overall"] = {
            "round2_final_score_mean": round(statistics.mean(all_r2_means), 1),
            "round2_avg_std": round(statistics.mean(all_r2_stds), 1) if all_r2_stds else 0,
            "round1_avg_std": round(statistics.mean(all_r1_stds), 1) if all_r1_stds else 0,
            "std_improvement": round(
                statistics.mean(all_r1_stds) - statistics.mean(all_r2_stds), 1
            ) if all_r1_stds and all_r2_stds else 0,
            "dimensions_converged": sum(1 for s in all_r2_stds if s <= 8),
            "dimensions_total": len(all_r2_stds),
        }

    return round2_result


# ── 合并 R1 + R2 ──

def merge_rounds(round1: dict, round2: dict) -> dict:
    """合并 R1 和 R2 结果为自包含 JSON"""
    merged = {
        "paper": round1["paper"],
        "framework": round1.get("framework", ""),
        "models": round1.get("models", []),
        "precheck": round1.get("precheck"),
        "dimensions": {},
        "overall": {},
    }

    r1_dims = round1.get("dimensions", {})
    r2_dims = round2.get("dimensions", {}) if round2 else {}

    for dim_key, r1_data in r1_dims.items():
        r2_data = r2_dims.get(dim_key, {})
        merged["dimensions"][dim_key] = {
            "round1_scores": r1_data.get("model_scores", {}),
            "round2_scores": r2_data.get("round2_scores", {}),
            "changes": r2_data.get("changes", {}),
            "round1_mean": r1_data.get("mean"),
            "round1_std": r1_data.get("std"),
            "round2_mean": r2_data.get("round2_mean"),
            "round2_std": r2_data.get("round2_std"),
            "convergence_improvement": r2_data.get("convergence_improvement"),
            "confidence": r1_data.get("confidence"),
            "raw_outputs": r1_data.get("raw_outputs", {}),
        }

    # 合并总体统计
    r1_overall = round1.get("overall", {})
    r2_overall = round2.get("overall", {}) if round2 else {}

    merged["overall"] = {
        "round1_avg_std": r2_overall.get("round1_avg_std"),
        "round2_avg_std": r2_overall.get("round2_avg_std"),
        "std_improvement": r2_overall.get("std_improvement"),
        "dimensions_converged": r2_overall.get("dimensions_converged"),
        "dimensions_total": r2_overall.get("dimensions_total"),
        "round1_final_score_mean": r1_overall.get("aggregation_mean", {}).get("final_score"),
        "round1_final_score_strictest": r1_overall.get("aggregation_strictest", {}).get("final_score"),
        "round2_final_score_mean": r2_overall.get("round2_final_score_mean"),
        "max_std": r1_overall.get("max_std"),
    }

    # 自主知识体系信号
    merged["autonomous_knowledge_signals"] = round1.get("autonomous_knowledge_signals")

    return merged


# ── 单篇完整流程 ──

async def evaluate_single_paper(
    paper: dict,
    framework_path: str,
    framework: Framework,
    providers_list: list,
    providers_dict: dict,
    output_path: Path,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger,
) -> dict | None:
    """对单篇论文执行完整 E1（R1 + R2）"""
    paper_id = paper['id']
    paper_path = paper['path']
    paper_name = paper['filename'][:60]

    # 断点续传
    if output_path.exists():
        logger.info(f"[E1] id={paper_id} {paper_name} → 跳过（已完成）")
        with open(output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async with semaphore:
        start_time = time.time()
        logger.info(f"[E1] id={paper_id} {paper_name} → 开始...")

        try:
            # Round 1
            r1_start = time.time()
            round1_result = await run_round1(
                paper_path, framework, providers_list, framework_path
            )
            r1_elapsed = time.time() - r1_start

            r1_score = round1_result.get("overall", {}).get("aggregation_mean", {}).get("final_score")
            r1_max_std = round1_result.get("overall", {}).get("max_std", "?")
            logger.info(
                f"[R1] id={paper_id} {paper_name} → "
                f"mean={r1_score} max_std={r1_max_std} 耗时={r1_elapsed:.0f}s"
            )

            # Round 2
            r2_start = time.time()
            r2_semaphore = asyncio.Semaphore(4)  # R2 维度级并发
            round2_result = await run_round2(
                paper_path, round1_result, framework,
                providers_dict, r2_semaphore, logger, paper_id
            )
            r2_elapsed = time.time() - r2_start

            r2_score = round2_result.get("overall", {}).get("round2_final_score_mean")
            r2_avg_std = round2_result.get("overall", {}).get("round2_avg_std")
            logger.info(
                f"[R2] id={paper_id} {paper_name} → "
                f"mean={r2_score} avg_std={r2_avg_std} 耗时={r2_elapsed:.0f}s"
            )

            # 合并
            merged = merge_rounds(round1_result, round2_result)
            total_elapsed = time.time() - start_time

            # 保存
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8'
            )

            logger.info(
                f"[E1] id={paper_id} {paper_name} → "
                f"完成 R1={r1_score} R2={r2_score} 总耗时={total_elapsed:.0f}s"
            )
            return merged

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            logger.error(f"[E1] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {error_msg}")

            # 记录内容审查问题
            if "data_inspection_failed" in error_msg or "content_policy" in error_msg:
                issues_path = output_path.parent.parent / "content_inspection_issues.jsonl"
                record = {
                    "paper_id": paper_id,
                    "paper_path": paper_path,
                    "error": error_msg,
                    "timestamp": datetime.now().isoformat(),
                }
                with open(issues_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

            return None


# ── 主入口 ──

async def main():
    parser = argparse.ArgumentParser(description="学术月刊 E1 评价")
    parser.add_argument("--input-dir", required=True, help="论文目录（MD 文件）")
    parser.add_argument("--framework", required=True, help="框架配置 YAML 文件")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="论文级并发数")
    parser.add_argument("--paper-ids", type=str, default=None, help="指定论文 ID（逗号分隔）")
    parser.add_argument("--paper-list", type=str, default=None, help="论文列表 JSON（可选，默认从目录生成）")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    round2_dir = output_dir / "round2"
    round2_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)

    # 加载框架
    framework = load_framework(args.framework)
    logger.info(f"框架: {framework.name} v{framework.version}")
    logger.info(f"维度: {[d.name_zh for d in framework.dimensions]}")

    # 生成或加载论文列表
    if args.paper_list:
        with open(args.paper_list, 'r', encoding='utf-8') as f:
            paper_data = json.load(f)
        papers = paper_data["papers"]
    else:
        papers = generate_paper_list(args.input_dir)
        # 保存论文列表
        paper_list_path = output_dir / "paper-list.json"
        with open(paper_list_path, 'w', encoding='utf-8') as f:
            json.dump({"total": len(papers), "papers": papers}, f, indent=2, ensure_ascii=False)

    # 过滤指定 ID
    if args.paper_ids:
        target_ids = set(int(x) for x in args.paper_ids.split(','))
        papers = [p for p in papers if p['id'] in target_ids]

    logger.info(f"论文: {len(papers)} 篇")
    logger.info(f"模型: {MODELS}")
    logger.info(f"并发: {args.concurrency}")
    logger.info(f"A 组（宽松）: {A_GROUP}")
    logger.info(f"B 组（严格）: {B_GROUP}")
    logger.info("")

    # 创建 providers
    providers_list = create_providers(MODELS)
    providers_dict = {p.model_name: p for p in providers_list}

    # 并发控制
    semaphore = asyncio.Semaphore(args.concurrency)

    # 执行
    start_time = time.time()
    tasks = []
    for paper in papers:
        output_path = round2_dir / f"paper-{paper['id']}.json"
        task = evaluate_single_paper(
            paper, args.framework, framework, providers_list,
            providers_dict, output_path, semaphore, logger
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    # 统计
    total_elapsed = time.time() - start_time
    success = sum(1 for r in results if r is not None)
    failed = len(results) - success

    # 生成摘要报告
    r1_scores = []
    r2_scores = []
    r1_stds = []
    r2_stds = []

    for r in results:
        if r:
            r1 = r.get("overall", {}).get("round1_final_score_mean")
            r2 = r.get("overall", {}).get("round2_final_score_mean")
            std1 = r.get("overall", {}).get("round1_avg_std")
            std2 = r.get("overall", {}).get("round2_avg_std")
            if r1:
                r1_scores.append(r1)
            if r2:
                r2_scores.append(r2)
            if std1:
                r1_stds.append(std1)
            if std2:
                r2_stds.append(std2)

    report = {
        "journal": "学术月刊",
        "total_papers": len(papers),
        "completed": success,
        "failed": failed,
        "framework": args.framework,
        "models": MODELS,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(total_elapsed),
        "elapsed_human": f"{int(total_elapsed // 3600)}h {int((total_elapsed % 3600) // 60)}m",
        "round1": {
            "avg_score": round(statistics.mean(r1_scores), 1) if r1_scores else None,
            "avg_std": round(statistics.mean(r1_stds), 1) if r1_stds else None,
        },
        "round2": {
            "avg_score": round(statistics.mean(r2_scores), 1) if r2_scores else None,
            "avg_std": round(statistics.mean(r2_stds), 1) if r2_stds else None,
        },
        "timestamp": datetime.now().isoformat(),
    }

    report_path = output_dir / "e1-report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"E1 评价完成")
    logger.info(f"  完成: {success}/{len(papers)} 篇")
    logger.info(f"  失败: {failed} 篇")
    logger.info(f"  Round 1 平均分: {report['round1']['avg_score']}")
    logger.info(f"  Round 2 平均分: {report['round2']['avg_score']}")
    logger.info(f"  Round 1 平均 std: {report['round1']['avg_std']}")
    logger.info(f"  Round 2 平均 std: {report['round2']['avg_std']}")
    logger.info(f"  总耗时: {report['elapsed_human']}")
    logger.info(f"  报告: {report_path}")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
