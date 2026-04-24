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

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt, build_precheck_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml
import jsonschema


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
            # 模型偶尔返回非 dict 格式，记为错误
            errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"
            continue
        if score is not None:
            scores[provider.model_name] = int(score)

    # 计算 mean/std/置信度
    score_values = list(scores.values())
    mean = statistics.mean(score_values) if score_values else 0.0
    std = statistics.stdev(score_values) if len(score_values) > 1 else 0.0

    if std <= 5.0:
        confidence = "high"
    elif std <= 8.0:
        confidence = "medium"
    elif std <= 12.0:
        confidence = "low"
    else:
        confidence = "critical"

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
    """加载框架但跳过 schema 验证（YAML 可能缺少部分 schema 必需字段）"""
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


async def run_convergence_test(
    framework_path: str,
    paper_path: str,
    model_names: list[str],
    dimension_keys: list[str] | None = None,
    include_precheck: bool = True,
) -> dict:
    """运行完整的收敛测试"""
    framework = _load_framework_skip_validation(framework_path)
    paper = process_file(paper_path)
    providers = create_providers(model_names)

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
        "paper_structure_status": paper.structure_status,
    }

    # 前置检查（可选）
    if include_precheck and framework.precheck and not dimension_keys:
        print("运行前置检查...")
        result["precheck"] = await run_precheck(providers, framework, paper)
    else:
        result["precheck"] = None

    # 逐维度评估
    dimension_results = {}
    for dim in dimensions:
        print(f"评估维度：{dim.name_zh} ({dim.key})...")
        dim_result = await evaluate_single_dimension(
            providers, dim, paper, framework_path
        )
        dimension_results[dim.key] = dim_result

        scores_str = ", ".join(
            f"{k}={v}" for k, v in dim_result["scores"].items()
        )
        print(f"  分数：{scores_str} | mean={dim_result['mean']} | std={dim_result['std']} | 置信度={dim_result['confidence']}")

    result["dimensions"] = dimension_results

    # 总体统计
    all_stds = [dr["std"] for dr in dimension_results.values()]
    all_means = [dr["mean"] for dr in dimension_results.values()]
    high_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "high"
    )

    # 加权总分
    weighted_total = 0.0
    for dim in dimensions:
        dr = dimension_results[dim.key]
        weighted_total += dr["mean"] * dim.weight

    result["overall"] = {
        "avg_std": round(statistics.mean(all_stds) if all_stds else 0.0, 1),
        "max_std": round(max(all_stds) if all_stds else 0.0, 1),
        "weighted_total": round(weighted_total, 1),
        "high_confidence_pct": round(
            high_confidence_count / len(dimension_results) * 100 if dimension_results else 0.0, 1
        ),
        "dimension_count": len(dimension_results),
    }

    # 计算复合得分（用于 autoresearch）
    # composite_score = -avg_std + 10 * high_confidence_ratio
    # 目标：avg_std < 5, high_confidence_ratio > 0.8 → composite_score > 3.0
    high_confidence_ratio = high_confidence_count / len(dimension_results) if dimension_results else 0.0
    composite_score = -result["overall"]["avg_std"] + 10 * high_confidence_ratio
    result["overall"]["composite_score"] = round(composite_score, 2)

    # 最高 std 维度（优先优化目标）
    if dimension_results:
        worst_dim = max(dimension_results.values(), key=lambda d: d["std"])
        result["overall"]["worst_dimension"] = worst_dim["dimension"]
        result["overall"]["worst_std"] = worst_dim["std"]

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
        print(f"加权总分：{overall['weighted_total']}")
        print(f"平均 std：{overall['avg_std']}")
        print(f"最大 std：{overall['max_std']}")
        print(f"高置信度比例：{overall['high_confidence_pct']}%")
        print(f"复合得分：{overall['composite_score']}")
        if "worst_dimension" in overall:
            print(f"最高 std 维度：{overall['worst_dimension']} (std={overall['worst_std']})")


if __name__ == "__main__":
    main()