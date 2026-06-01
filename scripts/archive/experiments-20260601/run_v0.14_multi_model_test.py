"""v0.14 多模型验证测试脚本

用于验证 v0.14 评审规程在"中国自主知识体系"框架下的多模型稳定性。

测试流程：
1. 阶段 1：三中国模型并发评价（GLM-5.1, Qwen3.6-Plus, DeepSeek-v4-pro）
2. 阶段 2：如果 std > 8，触发 GPT 复核模型复核
3. 生成详细的测试报告

用法：
    # 测试单篇论文
    python scripts/run_v0.14_multi_model_test.py \
        --paper raw/holdout-test/数字法学的理论表达_马长山.pdf \
        --output results/v0.14-test-single.json

    # 批量测试（使用预定义样本列表）
    python scripts/run_v0.14_multi_model_test.py \
        --batch \
        --output-dir results/v0.14-batch-test/

    # 只运行三模型，不触发 GPT 复核
    python scripts/run_v0.14_multi_model_test.py \
        --paper raw/holdout-test/数字法学的理论表达_马长山.pdf \
        --no-gpt-review \
        --output results/v0.14-test-no-gpt.json
"""

# ruff: noqa: E402

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中。脚本已归档到 scripts/archive/experiments-20260601/。
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt, build_precheck_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml

# 信号校验（如果框架配置了 autonomous_knowledge_signals）
from src.evaluation.signal_check import run_signal_check


# ============================================================================
# 配置
# ============================================================================

# 默认框架配置（v0.16 规程对应 v2.46 大规模评估候选版，现为历史归档文件）
DEFAULT_FRAMEWORK = (
    "configs/frameworks/archive/v2.0-v2.54-20260522/law-v2.46-20260511.yaml"
)

# 两中国模型（仅 GLM + Qwen，不含 DeepSeek）
CHINA_MODELS = ["glm-5.1", "qwen3.6-plus"]

# GPT 复核模型（GPT-5.5，走 Zenmux）
DEFAULT_REVIEW_MODELS = ["gpt-5.5"]

# 分歧阈值
STD_THRESHOLD_MEDIUM = 5.0  # 高置信度上限
STD_THRESHOLD_LOW = 8.0     # 中等置信度上限
STD_THRESHOLD_CRITICAL = 12.0  # 低置信度上限

# 预定义测试样本（按测试计划选择）
BATCH_TEST_SAMPLES = [
    {
        "path": "raw/holdout-test/数字法学的理论表达_马长山.pdf",
        "type": "理论建构型",
        "signal": "强",
        "description": "测试理论型论文的分歧 + 中国模型优势"
    },
    {
        "path": "raw/holdout-test/善终、凶死与杀人偿命——中国人死刑观念的文化阐释_尚海明.pdf",
        "type": "文化阐释型",
        "signal": "强",
        "description": "测试文化阐释型的分歧 + 中国模型优势"
    },
    {
        "path": "raw/holdout-test/股东会与董事会分权制度研究_许可.pdf",
        "type": "传统法学论证型",
        "signal": "中",
        "description": "基线稳定性测试"
    },
    {
        "path": "raw/holdout-test/法典化时代的刑法典修订_周光权.pdf",
        "type": "制度立法型",
        "signal": "中",
        "description": "测试制度型论文的分歧"
    },
    {
        "path": "raw/validation/迈向自主法学知识体系的比较法研究范式——以2003-2022年的比较法论文为样本_宋亚辉.pdf",
        "type": "理论建构型",
        "signal": "强",
        "description": "直接涉及'自主知识体系'概念"
    },
    {
        "path": "raw/validation/法秩序统一性原理之建构_雷磊.pdf",
        "type": "理论建构型",
        "signal": "中",
        "description": "测试理论建构的稳定性"
    },
]


# ============================================================================
# 辅助函数
# ============================================================================

async def _call_provider(provider, prompt: str) -> tuple[dict | None, str | None, float]:
    """调用单个 provider，返回 (raw_json, error, elapsed_seconds)"""
    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
        elapsed = time.time() - start
        return raw, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return None, str(e), elapsed


def _calculate_confidence(std: float) -> str:
    """根据标准差计算置信度"""
    if std <= STD_THRESHOLD_MEDIUM:
        return "high"
    elif std <= STD_THRESHOLD_LOW:
        return "medium"
    elif std <= STD_THRESHOLD_CRITICAL:
        return "low"
    else:
        return "critical"


def _compute_bonus(extension_substance: int, text_coherence: int) -> int:
    """确定性加分映射：(延展实质度, 正文衔接度) → bonus (0-5)"""
    if extension_substance == 0:
        return 0
    if extension_substance == 1:
        return 1 if text_coherence >= 3 else 0
    if extension_substance == 2:
        return 2 if text_coherence >= 3 else 1
    if extension_substance == 3:
        return 3 if text_coherence >= 3 else 2
    if extension_substance >= 4:
        return 5 if text_coherence >= 3 else 4
    return 0


def _extract_checklist_scores(score_rationale: str) -> tuple[int, int]:
    """从 score_rationale 中提取延展实质度和正文衔接度分数"""
    import re
    substance_match = re.search(r'延展实质度[=:](\d)/4', score_rationale)
    coherence_match = re.search(r'正文衔接度[=:](\d)/4', score_rationale)
    substance = int(substance_match.group(1)) if substance_match else 0
    coherence = int(coherence_match.group(1)) if coherence_match else 0
    return substance, coherence


def compute_layered_score(
    dimension_results: dict,
    framework: Framework,
) -> dict:
    """计算分层计分：基础分 + 加分 + 上限 + 最终分"""
    # 1. 基础分 = 前4维加权平均（归一化到 0-100）
    core_dim_keys = ["problem_originality", "literature_insight",
                     "analytical_framework", "logical_coherence"]
    core_weight_sum = 0.0
    base_raw = 0.0
    for dim in framework.dimensions:
        if dim.key in core_dim_keys:
            dr = dimension_results.get(dim.key)
            if dr:
                base_raw += dr["mean"] * dim.weight
                core_weight_sum += dim.weight

    base_score = round(base_raw / core_weight_sum, 1) if core_weight_sum else 0.0

    # 2. 结论可接受性上限
    conclusion_score = dimension_results.get("conclusion_consensus", {}).get("mean", 0)
    if conclusion_score >= 75:
        ceiling = None
    elif conclusion_score >= 60:
        ceiling = 75
    else:
        ceiling = 65

    # 3. 前瞻延展性加分
    fe_dr = dimension_results.get("forward_extension", {})
    fe_mean = fe_dr.get("mean", 0)

    # 尝试从 score_rationale 提取延展实质度和正文衔接度
    substance, coherence = 0, 0
    for model_name, raw_output in fe_dr.get("raw_outputs", {}).items():
        if isinstance(raw_output, dict):
            rationale = raw_output.get("score_rationale", "")
            s, c = _extract_checklist_scores(rationale)
            substance = max(substance, s)
            coherence = max(coherence, c)

    # 从 checklist 计算确定性 bonus
    checklist_bonus = _compute_bonus(substance, coherence)

    # 从原始分数映射 bonus（回退方案）
    score_bonus = 0
    if fe_mean >= 80:
        score_bonus = 5
    elif fe_mean >= 60:
        score_bonus = 3
    elif fe_mean >= 40:
        score_bonus = 2

    # 优先使用 checklist bonus（如果提取成功）
    bonus = checklist_bonus if substance > 0 else score_bonus

    # 前提条件检查
    logical_score = dimension_results.get("logical_coherence", {}).get("mean", 0)
    conclusion_min = conclusion_score
    core_min = min(
        dimension_results.get(k, {}).get("mean", 0) for k in core_dim_keys
    )
    prerequisites_met = (
        logical_score >= 60
        and conclusion_min >= 60
        and core_min >= 50
    )
    if not prerequisites_met:
        bonus = 0

    # 4. 最终分
    final_score = min(base_score + bonus, ceiling) if ceiling else base_score + bonus

    return {
        "base_score": base_score,
        "bonus_score": bonus,
        "bonus_source": "checklist" if checklist_bonus > 0 else "score_mapping",
        "extension_substance": substance,
        "text_coherence": coherence,
        "conclusion_ceiling": ceiling,
        "prerequisites_met": prerequisites_met,
        "final_score": round(final_score, 1),
        "fe_mean_0_100": fe_mean,
    }


def _load_framework_skip_validation(framework_path: str) -> Framework:
    """加载框架但跳过 schema 验证"""
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


# ============================================================================
# 核心评估函数
# ============================================================================

async def run_precheck(providers, framework, paper) -> dict:
    """运行前置检查（v2.45+ 自动适配 v0.14 §7.2 契约字段）"""
    from src.evaluation.precheck import PrecheckResult, _adapt_to_v014_contract

    prompt = build_precheck_prompt(framework, paper)

    results = await asyncio.gather(
        *[_call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    precheck_results = {}
    for (raw, error, elapsed), provider in zip(results, providers):
        if error:
            precheck_results[provider.model_name] = {
                "error": error,
                "elapsed": elapsed
            }
            continue

        # v2.45 契约适配：在 framework 声明 autonomous_knowledge_signals 时
        # 填充 conclusion / enter_six_dimension_review 等字段（v0.14 §7.2）
        adapted = raw
        try:
            pc_result = PrecheckResult(**raw)
            pc_adapted = _adapt_to_v014_contract(pc_result, framework)
            adapted = pc_adapted.model_dump(exclude_none=True)
        except Exception as exc:
            # 遗留字段校验失败（例如返回结构异常）时保留原始 raw，避免丢数据
            adapted = dict(raw)
            adapted["_adapt_error"] = str(exc)

        precheck_results[provider.model_name] = {
            "result": adapted,
            "elapsed": elapsed
        }

    return precheck_results


async def evaluate_single_dimension(
    providers, dimension, paper, framework_path: str
) -> dict:
    """并发调用所有 provider 评估单个维度"""
    prompt = build_prompt(dimension, paper)

    results = await asyncio.gather(
        *[_call_provider(p, prompt) for p in providers],
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
            errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"
            continue
        if score is not None:
            scores[provider.model_name] = int(score)

    # 计算 mean/std/置信度
    score_values = list(scores.values())
    mean = statistics.mean(score_values) if score_values else 0.0
    std = statistics.stdev(score_values) if len(score_values) > 1 else 0.0
    confidence = _calculate_confidence(std)

    return {
        "dimension": dimension.key,
        "name_zh": dimension.name_zh,
        "scores": scores,
        "mean": round(mean, 1),
        "std": round(std, 1),
        "confidence": confidence,
        "raw_outputs": raw_outputs,
        "errors": errors,
        "elapsed_times": elapsed_times,
    }


async def run_gpt_review(
    paper, framework, dimension_results: dict,
    trigger_reason: str, review_models: list[str],
) -> dict:
    """运行 GPT 复核（支持多模型对比），分歧超阈值时触发"""
    model_names_str = ", ".join(review_models)
    print(f"\n触发 GPT 复核（{model_names_str}）：{trigger_reason}")

    review_providers = create_providers(review_models)

    # 对所有维度并发调用所有复核模型
    gpt_dimension_results = {}
    for dim in framework.dimensions:
        dim_result = dimension_results.get(dim.key)
        if not dim_result:
            continue

        prompt = build_prompt(dim, paper)
        print(f"  复核维度：{dim.name_zh} ({dim.key})...")

        # 并发调用所有复核模型
        raw_calls = await asyncio.gather(
            *[_call_provider(p, prompt) for p in review_providers],
            return_exceptions=False,
        )

        dim_review = {
            "china_models_mean": dim_result["mean"],
            "china_models_std": dim_result["std"],
            "models": {},
        }

        review_scores = []
        for (raw, error, elapsed), provider in zip(raw_calls, review_providers):
            if error:
                dim_review["models"][provider.model_name] = {
                    "error": error, "elapsed": elapsed,
                }
                continue

            score = raw.get("score") if isinstance(raw, dict) else None
            if score is not None:
                score = int(score)
                review_scores.append(score)

            dim_review["models"][provider.model_name] = {
                "score": score,
                "raw_output": raw,
                "elapsed": elapsed,
                "deviation_from_china_mean": (
                    abs(score - dim_result["mean"]) if score else None
                ),
            }

        # 复核模型组统计
        if len(review_scores) > 1:
            dim_review["review_mean"] = round(statistics.mean(review_scores), 1)
            dim_review["review_std"] = round(statistics.stdev(review_scores), 1)
        elif review_scores:
            dim_review["review_mean"] = review_scores[0]
            dim_review["review_std"] = 0.0

        # 全部模型（中国 + 复核）综合统计
        china_scores = list(dim_result["scores"].values())
        all_scores = china_scores + review_scores
        if len(all_scores) > 1:
            dim_review["all_mean"] = round(statistics.mean(all_scores), 1)
            dim_review["all_std"] = round(statistics.stdev(all_scores), 1)
        elif all_scores:
            dim_review["all_mean"] = all_scores[0]
            dim_review["all_std"] = 0.0

        scores_str = ", ".join(
            f"{k}={v}" for k, v in
            {m: d["score"] for m, d in dim_review["models"].items() if "score" in d}.items()
        )
        print(f"    复核分数：{scores_str}")
        if "review_mean" in dim_review:
            print(f"    复核 mean={dim_review['review_mean']}, std={dim_review['review_std']}")
        if "all_mean" in dim_review:
            print(f"    综合 mean={dim_review['all_mean']}, all_std={dim_review['all_std']}")

        gpt_dimension_results[dim.key] = dim_review

    # 加权总分对比
    def _weighted_total(scores_by_dim_key: dict) -> float:
        total = 0.0
        for dim in framework.dimensions:
            s = scores_by_dim_key.get(dim.key)
            if s is not None:
                total += s * dim.weight
        return total

    # 中国模型加权总分（从 dimension_results 计算）
    china_weighted_total = 0.0
    for dim in framework.dimensions:
        dr = dimension_results.get(dim.key)
        if dr:
            china_weighted_total += dr["mean"] * dim.weight

    # 各复核模型的加权总分
    review_weighted_totals = {}
    for model_name in review_models:
        model_scores = {}
        for dim_key, dim_review in gpt_dimension_results.items():
            model_data = dim_review["models"].get(model_name)
            if model_data and "score" in model_data:
                model_scores[dim_key] = model_data["score"]
        review_weighted_totals[model_name] = round(
            _weighted_total(model_scores), 1
        )

    return {
        "triggered": True,
        "trigger_reason": trigger_reason,
        "review_models": review_models,
        "dimensions": gpt_dimension_results,
        "china_weighted_total": round(china_weighted_total, 1),
        "review_weighted_totals": review_weighted_totals,
    }


async def run_single_paper_test(
    paper_path: str,
    framework_path: str = DEFAULT_FRAMEWORK,
    model_names: list[str] = None,
    enable_gpt_review: bool = True,
    review_models: list[str] = None,
    paper_metadata: dict = None
) -> dict:
    """运行单篇论文的完整测试"""
    if model_names is None:
        model_names = CHINA_MODELS
    if review_models is None:
        review_models = DEFAULT_REVIEW_MODELS

    print(f"\n{'='*80}")
    print(f"测试论文：{paper_path}")
    if paper_metadata:
        print(f"论文类型：{paper_metadata.get('type', '未知')}")
        print(f"中国自主知识体系信号：{paper_metadata.get('signal', '未知')}")
    print(f"{'='*80}\n")

    # 加载框架和论文
    framework = _load_framework_skip_validation(framework_path)
    paper = process_file(paper_path)
    providers = create_providers(model_names)

    result = {
        "framework": framework_path,
        "framework_version": framework.version,
        "paper": paper_path,
        "paper_metadata": paper_metadata or {},
        "models": model_names,
        "review_models": review_models,
        "paper_structure_status": paper.structure_status,
        "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 阶段 1：前置检查
    print("阶段 1：运行前置检查...")
    if framework.precheck:
        result["precheck"] = await run_precheck(providers, framework, paper)
        print("  前置检查完成")
    else:
        result["precheck"] = None
        print("  跳过前置检查（框架未配置）")

    # 阶段 2：六维评分
    print("\n阶段 2：运行六维评分...")
    dimension_results = {}
    for dim in framework.dimensions:
        print(f"  评估维度：{dim.name_zh} ({dim.key})...")
        dim_result = await evaluate_single_dimension(
            providers, dim, paper, framework_path
        )
        dimension_results[dim.key] = dim_result

        scores_str = ", ".join(
            f"{k}={v}" for k, v in dim_result["scores"].items()
        )
        print(f"    分数：{scores_str}")
        print(f"    mean={dim_result['mean']}, std={dim_result['std']}, 置信度={dim_result['confidence']}")

    result["dimensions"] = dimension_results

    # 计算总体统计
    all_stds = [dr["std"] for dr in dimension_results.values()]
    high_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "high"
    )
    medium_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "medium"
    )
    low_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "low"
    )
    critical_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "critical"
    )

    # 加权总分
    weighted_total = 0.0
    for dim in framework.dimensions:
        dr = dimension_results[dim.key]
        weighted_total += dr["mean"] * dim.weight

    # 分层计分（v0.14 规程要求）
    layered = compute_layered_score(dimension_results, framework)

    avg_std = statistics.mean(all_stds) if all_stds else 0.0
    max_std = max(all_stds) if all_stds else 0.0

    result["overall"] = {
        "avg_std": round(avg_std, 1),
        "max_std": round(max_std, 1),
        "weighted_total": round(weighted_total, 1),
        "high_confidence_count": high_confidence_count,
        "medium_confidence_count": medium_confidence_count,
        "low_confidence_count": low_confidence_count,
        "critical_confidence_count": critical_confidence_count,
        "high_confidence_pct": round(
            high_confidence_count / len(dimension_results) * 100 if dimension_results else 0.0, 1
        ),
        "dimension_count": len(dimension_results),
    }

    # 分层计分结果
    result["layered_score"] = layered

    # 阶段 3：信号校验（自主知识体系信号）
    print("\n阶段 3：运行自主知识体系信号校验...")
    raw_config = _load_framework_skip_validation(framework_path)
    signals_config = None
    if hasattr(raw_config, 'raw_config') and isinstance(raw_config, Framework):
        raw_yaml = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
        signals_config = raw_yaml.get("autonomous_knowledge_signals")
    else:
        # 如果 raw_config 是普通 dict
        if isinstance(raw_config, dict):
            signals_config = raw_config.get("autonomous_knowledge_signals")
        else:
            raw_yaml = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
            signals_config = raw_yaml.get("autonomous_knowledge_signals")

    if signals_config:
        try:
            signal_result = await run_signal_check(
                providers[0], framework, paper,
                task_id="v0.14-test", db=None,
            )
            # v0.14 §7.3 契约：扁平四类信号字段 + legacy signals 列表同时输出
            from src.evaluation.signal_check import signal_to_dict
            flat_payload = signal_to_dict(signal_result)
            flat_payload["signals"] = {
                s.signal_key: s.judgment for s in signal_result.signals
            }
            result["signal_check"] = flat_payload
            print("  信号校验完成")
            for s in signal_result.signals:
                print(f"    {s.signal_key}: {s.judgment}")
            if signal_result.triggers_review:
                print(f"    ⚠ 触发复核：{signal_result.review_reason}")
        except Exception as e:
            result["signal_check"] = {"error": str(e)}
            print(f"  信号校验失败：{e}")
    else:
        result["signal_check"] = None
        print("  跳过信号校验（框架未配置）")

    # 最高 std 维度
    if dimension_results:
        worst_dim = max(dimension_results.values(), key=lambda d: d["std"])
        result["overall"]["worst_dimension"] = worst_dim["dimension"]
        result["overall"]["worst_std"] = worst_dim["std"]

    print("\n总体统计：")
    print(f"  加权总分：{result['overall']['weighted_total']}")
    print(f"  基础分：{layered['base_score']}")
    print(f"  前瞻延展性加分：{layered['bonus_score']}/5 (来源：{layered['bonus_source']})")
    print(f"  结论可接受性上限：{layered['conclusion_ceiling'] or '无上限'}")
    print(f"  最终分：{layered['final_score']}")
    print(f"  加分前提：{'满足' if layered['prerequisites_met'] else '不满足'}")
    print(f"  平均 std：{result['overall']['avg_std']}")
    print(f"  最大 std：{result['overall']['max_std']}")
    print(f"  高置信度：{high_confidence_count}/{len(dimension_results)} ({result['overall']['high_confidence_pct']}%)")
    print(f"  中等置信度：{medium_confidence_count}/{len(dimension_results)}")
    print(f"  低置信度：{low_confidence_count}/{len(dimension_results)}")
    print(f"  关键分歧：{critical_confidence_count}/{len(dimension_results)}")

    # 阶段 3：GPT 复核（如果需要）
    if enable_gpt_review:
        trigger_reason = None

        # 触发条件 1：整体 std > 8
        if avg_std > STD_THRESHOLD_LOW:
            trigger_reason = f"整体平均 std ({avg_std}) > {STD_THRESHOLD_LOW}"

        # 触发条件 2：单维度 std > 12
        elif max_std > STD_THRESHOLD_CRITICAL:
            trigger_reason = f"单维度 std ({max_std}) > {STD_THRESHOLD_CRITICAL} (维度: {result['overall']['worst_dimension']})"

        # 触发条件 3：理论型/文化阐释型论文（预期高分歧）
        elif paper_metadata and paper_metadata.get("type") in ["理论建构型", "文化阐释型"]:
            trigger_reason = f"论文类型为 {paper_metadata.get('type')}（预期高分歧）"

        if trigger_reason:
            result["gpt_review"] = await run_gpt_review(
                paper, framework, dimension_results, trigger_reason, review_models
            )
        else:
            result["gpt_review"] = {
                "triggered": False,
                "reason": "未达到触发条件"
            }
            print("\n未触发 GPT 复核：未达到触发条件")
    else:
        result["gpt_review"] = {
            "triggered": False,
            "reason": "用户禁用"
        }
        print("\n跳过 GPT 复核（用户禁用）")

    return result


# ============================================================================
# 批量测试
# ============================================================================

async def run_batch_test(
    output_dir: str,
    framework_path: str = DEFAULT_FRAMEWORK,
    enable_gpt_review: bool = True,
    review_models: list[str] = None,
) -> dict:
    """批量测试预定义样本"""
    if review_models is None:
        review_models = DEFAULT_REVIEW_MODELS
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*80}")
    print(f"批量测试：{len(BATCH_TEST_SAMPLES)} 篇论文")
    print(f"输出目录：{output_dir}")
    print(f"{'='*80}\n")

    all_results = []

    for i, sample in enumerate(BATCH_TEST_SAMPLES, 1):
        print(f"\n[{i}/{len(BATCH_TEST_SAMPLES)}] 测试：{sample['path']}")

        # 运行单篇测试
        result = await run_single_paper_test(
            paper_path=sample["path"],
            framework_path=framework_path,
            enable_gpt_review=enable_gpt_review,
            review_models=review_models,
            paper_metadata={
                "type": sample["type"],
                "signal": sample["signal"],
                "description": sample["description"]
            }
        )

        # 保存单篇结果
        paper_name = Path(sample["path"]).stem
        output_file = output_path / f"{paper_name}.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  结果已保存：{output_file}")

        all_results.append(result)

    # 生成汇总报告
    summary = generate_summary_report(all_results)
    summary_file = output_path / "summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n汇总报告已保存：{summary_file}")

    return summary


def generate_summary_report(all_results: list[dict]) -> dict:
    """生成汇总报告"""
    summary = {
        "test_count": len(all_results),
        "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_statistics": {},
        "by_paper_type": {},
        "by_signal_strength": {},
        "gpt_review_statistics": {},
        "papers": []
    }

    # 整体统计
    all_avg_stds = [r["overall"]["avg_std"] for r in all_results]
    all_max_stds = [r["overall"]["max_std"] for r in all_results]
    all_weighted_totals = [r["overall"]["weighted_total"] for r in all_results]
    all_final_scores = [
        r.get("layered_score", {}).get("final_score")
        for r in all_results
        if r.get("layered_score", {}).get("final_score") is not None
    ]

    high_confidence_papers = sum(
        1 for r in all_results if r["overall"]["high_confidence_pct"] >= 50
    )

    summary["overall_statistics"] = {
        "avg_std_mean": round(statistics.mean(all_avg_stds), 1),
        "avg_std_median": round(statistics.median(all_avg_stds), 1),
        "max_std_mean": round(statistics.mean(all_max_stds), 1),
        "weighted_total_mean": round(statistics.mean(all_weighted_totals), 1),
        "final_score_mean": (
            round(statistics.mean(all_final_scores), 1) if all_final_scores else None
        ),
        "high_confidence_paper_count": high_confidence_papers,
        "high_confidence_paper_pct": round(high_confidence_papers / len(all_results) * 100, 1)
    }

    # 按论文类型统计
    by_type = {}
    for r in all_results:
        paper_type = r["paper_metadata"].get("type", "未知")
        if paper_type not in by_type:
            by_type[paper_type] = []
        by_type[paper_type].append(r["overall"]["avg_std"])

    for paper_type, stds in by_type.items():
        summary["by_paper_type"][paper_type] = {
            "count": len(stds),
            "avg_std_mean": round(statistics.mean(stds), 1)
        }

    # 按信号强度统计
    by_signal = {}
    for r in all_results:
        signal = r["paper_metadata"].get("signal", "未知")
        if signal not in by_signal:
            by_signal[signal] = []
        by_signal[signal].append(r["overall"]["avg_std"])

    for signal, stds in by_signal.items():
        summary["by_signal_strength"][signal] = {
            "count": len(stds),
            "avg_std_mean": round(statistics.mean(stds), 1)
        }

    # GPT 复核统计
    gpt_triggered_count = sum(
        1 for r in all_results if r["gpt_review"]["triggered"]
    )
    summary["gpt_review_statistics"] = {
        "triggered_count": gpt_triggered_count,
        "triggered_pct": round(gpt_triggered_count / len(all_results) * 100, 1)
    }

    # 论文列表
    for r in all_results:
        summary["papers"].append({
            "paper": r["paper"],
            "type": r["paper_metadata"].get("type"),
            "signal": r["paper_metadata"].get("signal"),
            "avg_std": r["overall"]["avg_std"],
            "max_std": r["overall"]["max_std"],
            "weighted_total": r["overall"]["weighted_total"],
            "final_score": r.get("layered_score", {}).get("final_score"),
            "high_confidence_pct": r["overall"]["high_confidence_pct"],
            "gpt_review_triggered": r["gpt_review"]["triggered"]
        })

    return summary


# ============================================================================
# 主函数
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v0.14 多模型验证测试")
    parser.add_argument(
        "--framework",
        default=DEFAULT_FRAMEWORK,
        help=f"评价框架 YAML 路径（默认：{DEFAULT_FRAMEWORK}）",
    )
    parser.add_argument(
        "--paper",
        default=None,
        help="单篇论文 PDF 路径（与 --batch 互斥）",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量测试预定义样本（与 --paper 互斥）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="单篇测试的输出 JSON 文件路径",
    )
    parser.add_argument(
        "--output-dir",
        default="results/v0.14-batch-test",
        help="批量测试的输出目录（默认：results/v0.14-batch-test）",
    )
    parser.add_argument(
        "--models",
        default=",".join(CHINA_MODELS),
        help=f"模型列表，逗号分隔（默认：{','.join(CHINA_MODELS)}）",
    )
    parser.add_argument(
        "--no-gpt-review",
        action="store_true",
        help="禁用 GPT 复核模型",
    )
    parser.add_argument(
        "--review-models",
        default=",".join(DEFAULT_REVIEW_MODELS),
        help=f"GPT 复核模型列表，逗号分隔（默认：{','.join(DEFAULT_REVIEW_MODELS)}，走 FUCHEERS）",
    )
    return parser


def main():
    parser = build_arg_parser()

    args = parser.parse_args()

    # 参数验证
    if args.batch and args.paper:
        parser.error("--batch 和 --paper 不能同时使用")

    if not args.batch and not args.paper:
        parser.error("必须指定 --paper 或 --batch")

    model_names = args.models.split(",")
    review_models = args.review_models.split(",")
    enable_gpt_review = not args.no_gpt_review

    if args.batch:
        # 批量测试
        result = asyncio.run(
            run_batch_test(
                output_dir=args.output_dir,
                framework_path=args.framework,
                enable_gpt_review=enable_gpt_review,
                review_models=review_models,
            )
        )

        print(f"\n{'='*80}")
        print("批量测试完成")
        print(f"{'='*80}")
        print(f"测试论文数：{result['test_count']}")
        print(f"平均 std（均值）：{result['overall_statistics']['avg_std_mean']}")
        print(f"平均 std（中位数）：{result['overall_statistics']['avg_std_median']}")
        print(f"高置信度论文：{result['overall_statistics']['high_confidence_paper_count']}/{result['test_count']} ({result['overall_statistics']['high_confidence_paper_pct']}%)")
        print(f"GPT 复核触发率：{result['gpt_review_statistics']['triggered_pct']}%")

    else:
        # 单篇测试
        if not args.output:
            ts = time.strftime("%Y%m%d-%H%M%S")
            paper_name = Path(args.paper).stem
            output_dir = PROJECT_ROOT / "results"
            output_dir.mkdir(exist_ok=True)
            args.output = str(output_dir / f"v0.14-test-{paper_name}-{ts}.json")

        result = asyncio.run(
            run_single_paper_test(
                paper_path=args.paper,
                framework_path=args.framework,
                model_names=model_names,
                enable_gpt_review=enable_gpt_review,
                review_models=review_models,
            )
        )

        # 保存结果
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(f"\n{'='*80}")
        print("测试完成")
        print(f"{'='*80}")
        print(f"结果已保存：{output_path}")


if __name__ == "__main__":
    main()
