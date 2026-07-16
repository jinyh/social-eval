"""三模型迭代收敛测试脚本

绕过数据库依赖，直接调用 Provider + Prompt Builder + Reliability Calculator，
输出 JSON 结果便于逐维度分析和优化。

用法：
    python scripts/run_convergence_test.py \
        --framework configs/frameworks/law-v2.8-20260423.yaml \
        --paper raw/司法公正与同理心正义_杜宴林.pdf \
        --models gpt-5.4,kimi-k2.6,glm-5.1 \
        --dimensions problem_originality  # 可选，默认全部
        --output results/convergence-test-1.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt, build_precheck_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.knowledge.schemas import Framework
from src.reporting.scoring import calculate_weighted_total


def aggregate_scores(model_scores: dict[str, float], mode: str) -> dict:
    """聚合多模型分数

    Args:
        model_scores: {model_name: score}
        mode: "mean" | "strictest" | "both"

    Returns:
        {
            "mean": float,
            "std": float,
            "strictest": float,
            "strictest_model": str,
            "model_scores": dict
        }
    """
    scores = list(model_scores.values())

    result = {"model_scores": model_scores}

    if not scores:
        # 所有模型均失败，返回空结果避免 statistics.mean([]) 崩溃
        result["mean"] = 0.0
        result["std"] = 0.0
        result["strictest"] = 0.0
        return result

    if mode in ["mean", "both"]:
        result["mean"] = round(statistics.mean(scores), 1)
        result["std"] = round(statistics.stdev(scores), 1) if len(scores) > 1 else 0.0

    if mode in ["strictest", "both"]:
        min_score = min(scores)
        result["strictest"] = min_score
        # 找到最低分对应的模型
        for model, score in model_scores.items():
            if score == min_score:
                result["strictest_model"] = model
                break

    return result


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


async def evaluate_single_dimension(
    providers, dimension, paper, framework_path: str, aggregation_mode: str = "mean"
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
            # 模型偶尔返回非 dict 格式，记为错误
            errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"
            continue
        if score is not None:
            scores[provider.model_name] = int(score)

    # 使用聚合函数计算分数
    aggregated = aggregate_scores(scores, aggregation_mode)

    # 计算置信度（基于 std）
    std = aggregated.get("std", 0.0)
    if std <= 5.0:
        confidence = "high"
    elif std <= 8.0:
        confidence = "medium"
    elif std <= 12.0:
        confidence = "low"
    else:
        confidence = "critical"

    result = {
        "dimension": dimension.key,
        "name_zh": dimension.name_zh,
        "confidence": confidence,
        "raw_outputs": raw_outputs,
        "errors": errors,
        "elapsed_times": elapsed_times,
    }

    # 合并聚合结果
    result.update(aggregated)

    return result


async def run_precheck(providers, framework, paper) -> dict:
    """运行前置检查"""
    prompt = build_precheck_prompt(framework, paper)

    results = await asyncio.gather(
        *[_call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    precheck_results = {}
    for (raw, error, elapsed), provider in zip(results, providers):
        if error:
            precheck_results[provider.model_name] = {"error": error}
        else:
            precheck_results[provider.model_name] = raw

    return precheck_results


def _load_framework_skip_validation(framework_path: str) -> Framework:
    """兼容旧函数名；所有活跃框架均执行 schema 验证。"""
    return load_framework(framework_path)


async def run_convergence_test(
    framework_path: str,
    paper_path: str,
    model_names: list[str],
    dimension_keys: list[str] | None = None,
    include_precheck: bool = True,
    aggregation_mode: str = "mean",
    provider_instances: list[Any] | None = None,
) -> dict:
    """运行完整的收敛测试

    Args:
        framework_path: 框架配置文件路径
        paper_path: 论文文件路径
        model_names: 模型名称列表
        dimension_keys: 要评估的维度列表（None 表示全部）
        include_precheck: 是否包含预检
        aggregation_mode: 聚合模式 "mean" | "strictest" | "both"
    """
    framework = _load_framework_skip_validation(framework_path)
    paper = process_file(paper_path)
    providers = provider_instances or create_providers(model_names)

    # 确定要评估的维度
    if dimension_keys:
        dimensions = [d for d in framework.dimensions if d.key in dimension_keys]
        if not dimensions:
            raise ValueError(f"未找到维度：{dimension_keys}")
    else:
        dimensions = framework.dimensions

    result = {
        "framework": framework_path,
        "framework_version": framework.version,
        "paper": paper_path,
        "models": model_names,
        "aggregation_mode": aggregation_mode,
        "paper_structure_status": paper.structure_status,
    }

    # 前置检查（可选）
    if include_precheck and framework.precheck and not dimension_keys:
        print("运行前置检查...")
        result["precheck"] = await run_precheck(providers, framework, paper)
    else:
        result["precheck"] = None

    # 并发评估所有维度（带并发控制，避免 API rate limiting）
    semaphore = asyncio.Semaphore(4)

    async def evaluate_with_limit(dim):
        async with semaphore:
            return await evaluate_single_dimension(providers, dim, paper, framework_path, aggregation_mode)

    print(f"评估 {len(dimensions)} 个维度（最多 4 个并发）...")
    dim_tasks = [evaluate_with_limit(dim) for dim in dimensions]
    dim_results_list = await asyncio.gather(*dim_tasks)

    dimension_results = {}
    for dim, dim_result in zip(dimensions, dim_results_list):
        dimension_results[dim.key] = dim_result

        # 打印日志
        if aggregation_mode == "both":
            scores_str = ", ".join(
                f"{k}={v}" for k, v in dim_result["model_scores"].items()
            )
            print(f"  {dim.name_zh} ({dim.key}): {scores_str} | mean={dim_result.get('mean')} | strictest={dim_result.get('strictest')} ({dim_result.get('strictest_model')}) | std={dim_result.get('std')} | 置信度={dim_result['confidence']}")
        elif aggregation_mode == "strictest":
            scores_str = ", ".join(
                f"{k}={v}" for k, v in dim_result["model_scores"].items()
            )
            print(f"  {dim.name_zh} ({dim.key}): {scores_str} | strictest={dim_result.get('strictest')} ({dim_result.get('strictest_model')}) | 置信度={dim_result['confidence']}")
        else:  # mean
            scores_str = ", ".join(
                f"{k}={v}" for k, v in dim_result["model_scores"].items()
            )
            print(f"  {dim.name_zh} ({dim.key}): {scores_str} | mean={dim_result.get('mean')} | std={dim_result.get('std')} | 置信度={dim_result['confidence']}")

    result["dimensions"] = dimension_results

    # 总体统计
    all_stds = [dr.get("std", 0.0) for dr in dimension_results.values()]
    high_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "high"
    )

    # 计算总分
    overall = {}

    if aggregation_mode in ["mean", "both"]:
        # Mean 模式总分
        dimension_means = {dim.key: dimension_results[dim.key].get("mean", 0) for dim in dimensions}
        scoring_protocol = framework.raw_config.get("scoring_protocol")
        final_score_mean = calculate_weighted_total(
            dimension_scores=dimension_means,
            scoring_protocol=scoring_protocol,
        )

        weighted_total_mean = sum(
            dimension_results[dim.key].get("mean", 0) * dim.weight for dim in dimensions
        )

        overall["aggregation_mean"] = {
            "final_score": final_score_mean,
            "weighted_total": round(weighted_total_mean, 1),
        }

    if aggregation_mode in ["strictest", "both"]:
        # Strictest 模式总分
        dimension_strictest = {dim.key: dimension_results[dim.key].get("strictest", 0) for dim in dimensions}
        scoring_protocol = framework.raw_config.get("scoring_protocol")
        final_score_strictest = calculate_weighted_total(
            dimension_scores=dimension_strictest,
            scoring_protocol=scoring_protocol,
        )

        weighted_total_strictest = sum(
            dimension_results[dim.key].get("strictest", 0) * dim.weight for dim in dimensions
        )

        overall["aggregation_strictest"] = {
            "final_score": final_score_strictest,
            "weighted_total": round(weighted_total_strictest, 1),
        }

    # 通用统计
    overall["avg_std"] = round(statistics.mean(all_stds) if all_stds else 0.0, 1)
    overall["max_std"] = round(max(all_stds) if all_stds else 0.0, 1)
    overall["high_confidence_pct"] = round(
        high_confidence_count / len(dimension_results) * 100 if dimension_results else 0.0, 1
    )
    overall["dimension_count"] = len(dimension_results)

    # 计算分数差距（仅在 both 模式下）
    if aggregation_mode == "both":
        score_gap = overall["aggregation_mean"]["final_score"] - overall["aggregation_strictest"]["final_score"]
        overall["score_gap"] = round(score_gap, 1)

    # 复合得分（用于 autoresearch）
    high_confidence_ratio = high_confidence_count / len(dimension_results) if dimension_results else 0.0
    composite_score = -overall["avg_std"] + 10 * high_confidence_ratio
    overall["composite_score"] = round(composite_score, 2)

    # 最高 std 维度（优先优化目标）
    if dimension_results:
        worst_dim = max(dimension_results.values(), key=lambda d: d.get("std", 0.0))
        overall["worst_dimension"] = worst_dim["dimension"]
        overall["worst_std"] = worst_dim.get("std", 0.0)

    # Legacy 兼容：如果是 mean 模式，保留旧的字段名
    if aggregation_mode == "mean":
        overall["final_score"] = overall["aggregation_mean"]["final_score"]
        overall["weighted_total"] = overall["aggregation_mean"]["weighted_total"]

    result["overall"] = overall

    return result


def main():
    parser = argparse.ArgumentParser(description="三模型迭代收敛测试")
    parser.add_argument(
        "--framework",
        default="configs/frameworks/law-v2.8-20260423.yaml",
        help="评价框架 YAML 路径",
    )
    parser.add_argument(
        "--paper",
        default="raw/司法公正与同理心正义_杜宴林.pdf",
        help="论文 PDF 路径",
    )
    parser.add_argument(
        "--models",
        default="gpt-5.4,kimi-k2.6,glm-5.1",
        help="模型列表，逗号分隔",
    )
    parser.add_argument(
        "--dimensions",
        default=None,
        help="只评估指定维度，逗号分隔（如 problem_originality）；默认全部",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出 JSON 文件路径；默认 results/convergence-test-<timestamp>.json",
    )
    parser.add_argument(
        "--no-precheck",
        action="store_true",
        help="跳过前置检查",
    )
    parser.add_argument(
        "--metric",
        default="standard",
        choices=["standard", "composite"],
        help="输出指标类型：standard=完整JSON，composite=单一复合得分（用于autoresearch）",
    )
    parser.add_argument(
        "--score-field",
        default="final_score",
        choices=["final_score", "weighted_total"],
        help="主分字段：final_score（默认，v0.16 规程）或 weighted_total（legacy）",
    )
    parser.add_argument(
        "--aggregation-mode",
        default="mean",
        choices=["mean", "strictest", "both"],
        help="聚合模式：mean（均值），strictest（最严格），both（同时计算两种）",
    )

    args = parser.parse_args()

    model_names = args.models.split(",")
    dimension_keys = args.dimensions.split(",") if args.dimensions else None

    if not args.output:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_dir = PROJECT_ROOT / "results"
        output_dir.mkdir(exist_ok=True)
        args.output = str(output_dir / f"convergence-test-{ts}.json")

    print(f"框架：{args.framework}")
    print(f"论文：{args.paper}")
    print(f"模型：{model_names}")
    print(f"维度：{dimension_keys or '全部'}")
    print()

    result = asyncio.run(
        run_convergence_test(
            framework_path=args.framework,
            paper_path=args.paper,
            model_names=model_names,
            dimension_keys=dimension_keys,
            include_precheck=not args.no_precheck,
            aggregation_mode=args.aggregation_mode,
        )
    )

    # 写入输出文件
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已保存到：{output_path}")

    # 打印汇总
    overall = result["overall"]

    if args.metric == "composite":
        # Autoresearch 模式：只输出单一数值
        print(f"\ncomposite_score: {overall['composite_score']}")
    else:
        # 标准模式：完整汇总
        print(f"\n=== 汇总 ===")

        if args.aggregation_mode == "both":
            print(f"--- Mean 聚合 ---")
            print(f"final_score：{overall['aggregation_mean']['final_score']}（主分）")
            print(f"weighted_total：{overall['aggregation_mean']['weighted_total']}（legacy）")
            print(f"\n--- Strictest 聚合 ---")
            print(f"final_score：{overall['aggregation_strictest']['final_score']}（主分）")
            print(f"weighted_total：{overall['aggregation_strictest']['weighted_total']}（legacy）")
            print(f"\n分数差距：{overall['score_gap']} 分")
        elif args.aggregation_mode == "strictest":
            print(f"final_score：{overall['aggregation_strictest']['final_score']}（主分）")
            print(f"weighted_total：{overall['aggregation_strictest']['weighted_total']}（legacy）")
        else:  # mean
            print(f"final_score：{overall.get('final_score', overall['aggregation_mean']['final_score'])}（主分）")
            print(f"weighted_total：{overall.get('weighted_total', overall['aggregation_mean']['weighted_total'])}（legacy）")

        print(f"\n平均 std：{overall['avg_std']}")
        print(f"最大 std：{overall['max_std']}")
        print(f"高置信度比例：{overall['high_confidence_pct']}%")
        print(f"复合得分：{overall['composite_score']}")
        if "worst_dimension" in overall:
            print(f"最高 std 维度：{overall['worst_dimension']} (std={overall['worst_std']})")


if __name__ == "__main__":
    main()
