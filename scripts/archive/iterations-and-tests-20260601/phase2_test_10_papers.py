#!/usr/bin/env python3
"""Phase 2 测试脚本：10 篇论文 Round 1 + Round 2 完整流程

基于前 100 篇的成功经验：
- 4 个模型（deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus）
- A 组（宽松）：glm-5.1, qwen3.6-plus
- B 组（严格）：deepseek-v4-pro, kimi-k2.6
- Round 1 + Round 2 使用同一框架的 prompt_template（含锚定规则）
- Round 2 在 Round 1 prompt 基础上追加交叉评审上下文

用法：
    python scripts/phase2_test_10_papers.py \
        --framework configs/frameworks/law-v2.56.6-20260522.yaml \
        --paper-list results/phase2-test-10-papers.json \
        --output-dir results/phase2-test-10 \
        --concurrency 5
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework
from src.reporting.scoring import calculate_weighted_total

import yaml

# 模型配置（与前 100 篇一致）
MODELS = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
A_GROUP = ['glm-5.1', 'qwen3.6-plus']  # 宽松组
B_GROUP = ['deepseek-v4-pro', 'kimi-k2.6']  # 严格组


def _paper_content(paper) -> str:
    """提取论文正文"""
    return paper.body or paper.full_text


def _reference_content(paper) -> str:
    """提取参考文献"""
    if not paper.references:
        return "（无）"
    return "\n".join(paper.references)


def build_cross_review_prompt(
    dimension,
    self_output: dict,
    other_group_outputs: list[dict],
    paper
) -> str:
    """构建交叉评审 prompt：复用 Round 1 的完整 prompt_template + 交叉评审上下文"""
    from src.evaluation.prompt_builder import build_prompt

    # 提取自己的评价
    self_score = self_output.get('score', 0)
    self_band = self_output.get('band', '')
    self_core_judgment = self_output.get('core_judgment', '')
    self_score_rationale = self_output.get('score_rationale', '')
    self_strengths = self_output.get('strengths', [])
    self_weaknesses = self_output.get('weaknesses', [])
    self_evidence_quotes = self_output.get('evidence_quotes', [])

    # 格式化自己的评价
    self_strengths_str = '\n'.join(f'  - {s}' for s in self_strengths) if self_strengths else '  （无）'
    self_weaknesses_str = '\n'.join(f'  - {w}' for w in self_weaknesses) if self_weaknesses else '  （无）'
    self_evidence_str = '\n'.join(f'  - {e}' for e in self_evidence_quotes) if self_evidence_quotes else '  （无）'

    # 构建对方组评价
    other_reviews = []
    for i, other_output in enumerate(other_group_outputs, 1):
        other_score = other_output.get('score', 0)
        other_band = other_output.get('band', '')
        other_core_judgment = other_output.get('core_judgment', '')
        other_score_rationale = other_output.get('score_rationale', '')
        other_strengths = other_output.get('strengths', [])
        other_weaknesses = other_output.get('weaknesses', [])
        other_evidence_quotes = other_output.get('evidence_quotes', [])

        other_strengths_str = '\n'.join(f'  - {s}' for s in other_strengths) if other_strengths else '  （无）'
        other_weaknesses_str = '\n'.join(f'  - {w}' for w in other_weaknesses) if other_weaknesses else '  （无）'
        other_evidence_str = '\n'.join(f'  - {e}' for e in other_evidence_quotes) if other_evidence_quotes else '  （无）'

        review = f"""【评审专家 {chr(64+i)}】
评分：{other_score}
评分档位：{other_band}
核心判断：{other_core_judgment}
评分理由：{other_score_rationale}
优点：
{other_strengths_str}
缺点：
{other_weaknesses_str}
证据引用：
{other_evidence_str}"""
        other_reviews.append(review)

    other_reviews_str = '\n\n'.join(other_reviews)

    # 获取 Round 1 的完整 prompt（含锚定规则 + 论文内容）
    round1_prompt = build_prompt(dimension, paper)

    # 拼接：交叉评审上下文 + Round 1 完整 prompt + 输出格式
    prompt = f"""【交叉评审模式 - 第二轮评分】

你之前对这篇论文的【{dimension.name_zh}】维度给出了以下评价：

【你的第一轮评价】
评分：{self_score}
评分档位：{self_band}
核心判断：{self_core_judgment}
评分理由：{self_score_rationale}
优点：
{self_strengths_str}
缺点：
{self_weaknesses_str}
证据引用：
{self_evidence_str}

---

现在，另一组评审专家对同一篇论文的同一维度给出了不同的评价：

{other_reviews_str}

---

请结合其他专家的意见，重新阅读论文并重新评分。
注意：
1. 其他专家的意见中是否有你之前忽略的合理观点？
2. 重新阅读论文后，你是否发现了之前遗漏的证据或论证？
3. 你是否需要修改你的评分？

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
以下是完整的评分标准和论文内容，请据此重新评分：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{round1_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
请按照以下 JSON 格式输出你的第二轮评价：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
  "score": <0-100 的整数>,
  "band": "<评分档位，如 A+/A/B+/B/C+/C/D>",
  "core_judgment": "<一句话核心判断>",
  "score_rationale": "<评分理由，说明为什么给这个分数>",
  "strengths": ["<优点1>", "<优点2>", ...],
  "weaknesses": ["<缺点1>", "<缺点2>", ...],
  "evidence_quotes": ["<证据引用1>", "<证据引用2>", ...],
  "revision_notes": "<说明你是否修改了评分，以及修改的原因>"
}}

注意：
- 如果你认为第一轮评价是合理的，可以保持原评分
- 如果你发现了新的证据或论证，应该修改评分
- revision_notes 字段必须说明你的决策过程
"""
    return prompt


def _load_framework(framework_path: str) -> Framework:
    """加载框架配置"""
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


async def _call_provider(provider, prompt: str, semaphore) -> tuple[dict | None, str | None, float]:
    """调用单个 provider，返回 (raw_json, error, elapsed_seconds)"""
    async with semaphore:
        start = time.time()
        try:
            raw = await provider.generate_json_response(prompt)
            elapsed = time.time() - start
            return raw, None, elapsed
        except Exception as e:
            elapsed = time.time() - start
            return None, str(e), elapsed


def aggregate_scores(model_scores: dict[str, float], mode: str) -> dict:
    """聚合多模型分数"""
    scores = list(model_scores.values())

    result = {"model_scores": model_scores}

    # 如果没有有效分数，返回空结果
    if not scores:
        if mode in ["mean", "both"]:
            result["mean"] = 0.0
            result["std"] = 0.0
        if mode in ["strictest", "both"]:
            result["strictest"] = 0.0
            result["strictest_model"] = None
        return result

    if mode in ["mean", "both"]:
        result["mean"] = round(statistics.mean(scores), 1)
        result["std"] = round(statistics.stdev(scores), 1) if len(scores) > 1 else 0.0

    if mode in ["strictest", "both"]:
        min_score = min(scores)
        result["strictest"] = min_score
        for model, score in model_scores.items():
            if score == min_score:
                result["strictest_model"] = model
                break

    return result


async def run_round1(framework, paper, providers, semaphore) -> dict:
    """执行 Round 1 评审（复用 run_convergence_test.py 的逻辑）"""
    from src.evaluation.prompt_builder import build_prompt

    dimensions = framework.dimensions

    print(f"  Round 1: 评估 {len(dimensions)} 个维度...")

    # 并发评估所有维度
    async def evaluate_dimension(dim):
        prompt = build_prompt(dim, paper)

        # 并发调用所有模型
        results = await asyncio.gather(
            *[_call_provider(p, prompt, semaphore) for p in providers],
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
                if score is not None:
                    scores[provider.model_name] = int(score)
            else:
                errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"

        # 聚合分数
        aggregated = aggregate_scores(scores, "both")

        # 计算置信度
        std = aggregated.get("std", 0.0)
        if std <= 5.0:
            confidence = "high"
        elif std <= 8.0:
            confidence = "medium"
        elif std <= 12.0:
            confidence = "low"
        else:
            confidence = "critical"

        dim_result = {
            "dimension": dim.key,
            "name_zh": dim.name_zh,
            "confidence": confidence,
            "raw_outputs": raw_outputs,
            "errors": errors,
            "elapsed_times": elapsed_times,
        }
        dim_result.update(aggregated)

        return dim_result

    # 并发评估所有维度
    dim_results_list = await asyncio.gather(*[evaluate_dimension(dim) for dim in dimensions])

    dimension_results = {}
    for dim, dim_result in zip(dimensions, dim_results_list):
        dimension_results[dim.key] = dim_result

        # 打印日志
        scores_str = ", ".join(f"{k}={v}" for k, v in dim_result["model_scores"].items())
        print(f"    {dim.name_zh}: {scores_str} | mean={dim_result.get('mean')} | std={dim_result.get('std')}")

    return dimension_results


async def run_round2(framework, paper, round1_results, providers, semaphore) -> dict:
    """执行 Round 2 交叉评审"""
    dimensions = framework.dimensions

    print(f"  Round 2: 交叉评审 {len(dimensions)} 个维度...")

    # 将 providers 转换为字典
    providers_dict = {p.model_name: p for p in providers}

    # 并发评估所有维度
    async def evaluate_dimension(dim):
        dim_key = dim.key
        dim_name = dim.name_zh

        # 获取 Round 1 的结果
        round1_dim = round1_results.get(dim_key, {})
        raw_outputs = round1_dim.get("raw_outputs", {})

        # Round 2 评审
        round2_scores = {}
        round2_raw_outputs = {}
        round2_errors = {}
        round2_elapsed_times = {}

        tasks = []
        task_models = []

        for model_name in MODELS:
            if model_name not in raw_outputs:
                continue

            # 确定对方组
            if model_name in A_GROUP:
                other_group = B_GROUP
            else:
                other_group = A_GROUP

            # 获取对方组的评价
            other_outputs = [raw_outputs[m] for m in other_group if m in raw_outputs]

            # 如果对方组没有成功的模型，直接复用 Round 1 的结果
            if not other_outputs:
                self_output = raw_outputs[model_name]
                round2_raw_outputs[model_name] = self_output
                score = self_output.get("score")
                if score is not None:
                    round2_scores[model_name] = int(score)
                continue

            # 构建交叉评审 prompt
            self_output = raw_outputs[model_name]
            prompt = build_cross_review_prompt(
                dimension=dim,
                self_output=self_output,
                other_group_outputs=other_outputs,
                paper=paper
            )

            # 调用 provider
            provider = providers_dict[model_name]
            tasks.append(_call_provider(provider, prompt, semaphore))
            task_models.append(model_name)

        # 并发执行
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=False)

            for (raw, error, elapsed), model_name in zip(results, task_models):
                round2_elapsed_times[model_name] = elapsed
                if error:
                    round2_errors[model_name] = error
                    continue
                round2_raw_outputs[model_name] = raw
                if isinstance(raw, dict):
                    score = raw.get("score")
                    if score is not None:
                        round2_scores[model_name] = int(score)
                    else:
                        round2_errors[model_name] = "Missing 'score' field in response"
                else:
                    round2_errors[model_name] = f"Unexpected output type: {type(raw).__name__}"

        # 如果 Round 2 没有任何有效分数，记录警告
        if not round2_scores:
            print(f"    警告：{dim.name_zh} Round 2 所有模型都失败")
            if round2_errors:
                for model, error in round2_errors.items():
                    print(f"      {model}: {error[:100]}")

        # 聚合分数
        aggregated = aggregate_scores(round2_scores, "both")

        # 计算置信度
        std = aggregated.get("std", 0.0)
        if std <= 5.0:
            confidence = "high"
        elif std <= 8.0:
            confidence = "medium"
        elif std <= 12.0:
            confidence = "low"
        else:
            confidence = "critical"

        dim_result = {
            "dimension": dim.key,
            "name_zh": dim.name_zh,
            "confidence": confidence,
            "raw_outputs": round2_raw_outputs,
            "errors": round2_errors,
            "elapsed_times": round2_elapsed_times,
        }
        dim_result.update(aggregated)

        return dim_result

    # 并发评估所有维度
    dim_results_list = await asyncio.gather(*[evaluate_dimension(dim) for dim in dimensions])

    dimension_results = {}
    for dim, dim_result in zip(dimensions, dim_results_list):
        dimension_results[dim.key] = dim_result

        # 打印日志
        scores_str = ", ".join(f"{k}={v}" for k, v in dim_result["model_scores"].items())
        round1_mean = round1_results[dim.key].get("mean", 0)
        round2_mean = dim_result.get("mean", 0)
        delta = round2_mean - round1_mean
        print(f"    {dim.name_zh}: {scores_str} | mean={round2_mean} (Δ{delta:+.1f}) | std={dim_result.get('std')}")

    return dimension_results


async def evaluate_paper(paper_info: dict, framework_path: str, output_dir: Path, concurrency: int):
    """评估单篇论文（Round 1 + Round 2）"""
    paper_id = paper_info["id"]
    paper_path = paper_info["path"]
    journal = paper_info["journal"]

    print(f"\n论文 {paper_id}: {Path(paper_path).stem[:60]}")
    print(f"  期刊: {journal}")

    # 用于记录内容审查问题
    content_inspection_issues = {
        "paper_id": paper_id,
        "paper_path": paper_path,
        "journal": journal,
        "round1_failures": {},
        "round2_failures": {}
    }

    # 检查是否已完成
    round1_output = output_dir / "round1" / f"paper-{paper_id}.json"
    round2_output = output_dir / "round2" / f"paper-{paper_id}.json"

    if round2_output.exists():
        print(f"  已完成，跳过")
        return

    # 加载框架和论文
    framework = _load_framework(framework_path)
    paper = process_file(paper_path)

    # 创建 providers
    providers = create_providers(MODELS)

    # 并发控制
    semaphore = asyncio.Semaphore(concurrency)

    # Round 1
    if not round1_output.exists():
        round1_results = await run_round1(framework, paper, providers, semaphore)

        # 检查 Round 1 是否有内容审查失败
        for dim_key, dim_data in round1_results.items():
            errors = dim_data.get("errors", {})
            for model_name, error_msg in errors.items():
                if "inappropriate content" in error_msg or "data_inspection_failed" in error_msg:
                    if dim_key not in content_inspection_issues["round1_failures"]:
                        content_inspection_issues["round1_failures"][dim_key] = []
                    content_inspection_issues["round1_failures"][dim_key].append(model_name)

        # 计算 Round 1 总分
        dimension_means = {dim.key: round1_results[dim.key].get("mean", 0) for dim in framework.dimensions}
        scoring_protocol = framework.raw_config.get("scoring_protocol")
        final_score_mean = calculate_weighted_total(
            dimension_scores=dimension_means,
            scoring_protocol=scoring_protocol,
        )

        dimension_strictest = {dim.key: round1_results[dim.key].get("strictest", 0) for dim in framework.dimensions}
        final_score_strictest = calculate_weighted_total(
            dimension_scores=dimension_strictest,
            scoring_protocol=scoring_protocol,
        )

        # 计算最大标准差
        all_stds = [round1_results[dim.key].get("std", 0.0) for dim in framework.dimensions]
        max_std = max(all_stds) if all_stds else 0.0

        overall_round1 = {
            "aggregation_mean": {"final_score": final_score_mean},
            "aggregation_strictest": {"final_score": final_score_strictest},
            "max_std": max_std,
        }

        # 保存 Round 1 结果
        round1_data = {
            "paper": paper_path,
            "paper_id": paper_id,
            "journal": journal,
            "framework": framework_path,
            "models": MODELS,
            "dimensions": round1_results,
            "overall": overall_round1,
            "timestamp": datetime.now().isoformat(),
        }

        round1_output.parent.mkdir(parents=True, exist_ok=True)
        with open(round1_output, 'w', encoding='utf-8') as f:
            json.dump(round1_data, f, indent=2, ensure_ascii=False)

        print(f"  Round 1 完成: mean={final_score_mean:.1f}, strictest={final_score_strictest:.1f}, max_std={max_std:.1f}")
    else:
        # 加载 Round 1 结果
        with open(round1_output, 'r', encoding='utf-8') as f:
            round1_data = json.load(f)
        round1_results = round1_data["dimensions"]

        # 检查已有的 Round 1 结果中的内容审查失败
        for dim_key, dim_data in round1_results.items():
            errors = dim_data.get("errors", {})
            for model_name, error_msg in errors.items():
                if "inappropriate content" in error_msg or "data_inspection_failed" in error_msg:
                    if dim_key not in content_inspection_issues["round1_failures"]:
                        content_inspection_issues["round1_failures"][dim_key] = []
                    content_inspection_issues["round1_failures"][dim_key].append(model_name)

        print(f"  Round 1 已存在，跳过")

    # Round 2
    round2_results = await run_round2(framework, paper, round1_results, providers, semaphore)

    # 检查 Round 2 是否有内容审查失败
    for dim_key, dim_data in round2_results.items():
        errors = dim_data.get("errors", {})
        for model_name, error_msg in errors.items():
            if "inappropriate content" in error_msg or "data_inspection_failed" in error_msg:
                if dim_key not in content_inspection_issues["round2_failures"]:
                    content_inspection_issues["round2_failures"][dim_key] = []
                content_inspection_issues["round2_failures"][dim_key].append(model_name)

    # 计算 Round 2 总分
    dimension_means = {dim.key: round2_results[dim.key].get("mean", 0) for dim in framework.dimensions}
    scoring_protocol = framework.raw_config.get("scoring_protocol")
    final_score_mean = calculate_weighted_total(
        dimension_scores=dimension_means,
        scoring_protocol=scoring_protocol,
    )

    dimension_strictest = {dim.key: round2_results[dim.key].get("strictest", 0) for dim in framework.dimensions}
    final_score_strictest = calculate_weighted_total(
        dimension_scores=dimension_strictest,
        scoring_protocol=scoring_protocol,
    )

    # 计算最大标准差
    all_stds = [round2_results[dim.key].get("std", 0.0) for dim in framework.dimensions]
    max_std = max(all_stds) if all_stds else 0.0

    overall_round2 = {
        "aggregation_mean": {"final_score": final_score_mean},
        "aggregation_strictest": {"final_score": final_score_strictest},
        "max_std": max_std,
    }

    # 保存 Round 2 结果
    round2_data = {
        "paper": paper_path,
        "paper_id": paper_id,
        "journal": journal,
        "framework": framework_path,
        "models": MODELS,
        "dimensions": round2_results,
        "overall": overall_round2,
        "timestamp": datetime.now().isoformat(),
    }

    round2_output.parent.mkdir(parents=True, exist_ok=True)
    with open(round2_output, 'w', encoding='utf-8') as f:
        json.dump(round2_data, f, indent=2, ensure_ascii=False)

    print(f"  Round 2 完成: mean={final_score_mean:.1f}, strictest={final_score_strictest:.1f}, max_std={max_std:.1f}")

    # 如果有内容审查问题，记录到单独的文件
    if content_inspection_issues["round1_failures"] or content_inspection_issues["round2_failures"]:
        issues_file = output_dir / "content_inspection_issues.jsonl"
        with open(issues_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(content_inspection_issues, ensure_ascii=False) + "\n")
        print(f"  ⚠️  检测到内容审查问题，已记录到 {issues_file.name}")


async def main():
    parser = argparse.ArgumentParser(description="Phase 2 测试脚本：10 篇论文 Round 1 + Round 2")
    parser.add_argument(
        "--framework",
        type=str,
        default="configs/frameworks/law-v2.55-cross-review.yaml",
        help="框架配置文件路径"
    )
    parser.add_argument(
        "--paper-list",
        type=str,
        default="results/phase2-test-10-papers.json",
        help="论文列表文件路径"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/phase2-test-10"),
        help="输出目录"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="并发数"
    )

    args = parser.parse_args()

    # 读取论文列表
    with open(args.paper_list, 'r', encoding='utf-8') as f:
        paper_list = json.load(f)

    papers = paper_list["papers"]

    print(f"开始评审 {len(papers)} 篇论文")
    print(f"框架: {args.framework}")
    print(f"模型: {', '.join(MODELS)}")
    print(f"输出目录: {args.output_dir}")
    print(f"并发数: {args.concurrency}")

    # 论文级并发评审（最多 3 篇并发）
    paper_semaphore = asyncio.Semaphore(3)

    async def evaluate_with_limit(paper_info):
        async with paper_semaphore:
            try:
                await evaluate_paper(paper_info, args.framework, args.output_dir, args.concurrency)
            except Exception as e:
                print(f"  论文 {paper_info['id']} 错误: {e}")
                import traceback
                traceback.print_exc()

    tasks = [evaluate_with_limit(paper_info) for paper_info in papers]
    await asyncio.gather(*tasks)

    print(f"\n所有论文评审完成！")

    # 生成内容审查问题汇总报告
    issues_file = args.output_dir / "content_inspection_issues.jsonl"
    if issues_file.exists():
        print(f"\n生成内容审查问题汇总报告...")

        issues_list = []
        with open(issues_file, 'r', encoding='utf-8') as f:
            for line in f:
                issues_list.append(json.loads(line))

        # 生成 Markdown 报告
        report_lines = [
            "# 内容审查问题汇总报告",
            "",
            f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**问题论文数**：{len(issues_list)} 篇",
            "",
            "## 问题论文列表",
            "",
        ]

        for issue in issues_list:
            paper_name = Path(issue["paper_path"]).stem
            report_lines.append(f"### 论文 {issue['paper_id']}: {paper_name}")
            report_lines.append(f"- **期刊**：{issue['journal']}")
            report_lines.append(f"- **路径**：`{issue['paper_path']}`")
            report_lines.append("")

            if issue["round1_failures"]:
                report_lines.append("**Round 1 失败：**")
                for dim_key, models in issue["round1_failures"].items():
                    report_lines.append(f"- {dim_key}: {', '.join(models)}")
                report_lines.append("")

            if issue["round2_failures"]:
                report_lines.append("**Round 2 失败：**")
                for dim_key, models in issue["round2_failures"].items():
                    report_lines.append(f"- {dim_key}: {', '.join(models)}")
                report_lines.append("")

        # 统计分析
        report_lines.extend([
            "## 统计分析",
            "",
        ])

        # 按模型统计
        model_failure_count = {}
        for issue in issues_list:
            for dim_key, models in issue["round1_failures"].items():
                for model in models:
                    model_failure_count[model] = model_failure_count.get(model, 0) + 1
            for dim_key, models in issue["round2_failures"].items():
                for model in models:
                    model_failure_count[model] = model_failure_count.get(model, 0) + 1

        report_lines.append("### 按模型统计")
        report_lines.append("")
        for model, count in sorted(model_failure_count.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"- **{model}**: {count} 次失败")
        report_lines.append("")

        # 保存报告
        report_file = args.output_dir / "content_inspection_report.md"
        report_file.write_text("\n".join(report_lines), encoding='utf-8')
        print(f"  报告已保存：{report_file}")
        print(f"  详细日志：{issues_file}")


if __name__ == "__main__":
    asyncio.run(main())
