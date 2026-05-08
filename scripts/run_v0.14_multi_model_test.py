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
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml


# ============================================================================
# 配置
# ============================================================================

# 默认框架配置（v0.14 对应 v2.42）
DEFAULT_FRAMEWORK = "configs/frameworks/law-v2.42-20260507.yaml"

# 三中国模型
CHINA_MODELS = ["glm-5.1", "qwen3.6-plus", "deepseek-v4-pro"]

# GPT 复核模型（默认使用已验证可用的 Zenmux GPT-5.4）
DEFAULT_REVIEW_MODEL = "gpt-5.4"

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
    """运行前置检查"""
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
        else:
            precheck_results[provider.model_name] = {
                "result": raw,
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
    paper, framework, dimension_results: dict, trigger_reason: str, review_model: str
) -> dict:
    """运行 GPT 复核模型"""
    print(f"\n触发 GPT 复核模型（{review_model}）：{trigger_reason}")

    gpt_provider = create_providers([review_model])[0]

    # 对所有维度进行 GPT 复核评价
    gpt_dimension_results = {}
    for dim_key, dim_result in dimension_results.items():
        # 找到对应的 dimension 对象
        dimension = None
        for d in framework.dimensions:
            if d.key == dim_key:
                dimension = d
                break

        if not dimension:
            continue

        print(f"  GPT 复核模型评估维度：{dimension.name_zh} ({dim_key})...")
        prompt = build_prompt(dimension, paper)
        raw, error, elapsed = await _call_provider(gpt_provider, prompt)

        if error:
            gpt_dimension_results[dim_key] = {
                "error": error,
                "elapsed": elapsed
            }
        else:
            score = raw.get("score") if isinstance(raw, dict) else None
            gpt_dimension_results[dim_key] = {
                "score": score,
                "raw_output": raw,
                "elapsed": elapsed,
                "china_models_mean": dim_result["mean"],
                "china_models_std": dim_result["std"],
                "deviation": abs(score - dim_result["mean"]) if score else None
            }

    # 计算 GPT 复核模型的加权总分
    gpt_weighted_total = 0.0
    for dim in framework.dimensions:
        if dim.key in gpt_dimension_results and "score" in gpt_dimension_results[dim.key]:
            gpt_weighted_total += gpt_dimension_results[dim.key]["score"] * dim.weight

    return {
        "triggered": True,
        "trigger_reason": trigger_reason,
        "model": review_model,
        "dimensions": gpt_dimension_results,
        "weighted_total": round(gpt_weighted_total, 1)
    }


async def run_single_paper_test(
    paper_path: str,
    framework_path: str = DEFAULT_FRAMEWORK,
    model_names: list[str] = None,
    enable_gpt_review: bool = True,
    review_model: str = DEFAULT_REVIEW_MODEL,
    paper_metadata: dict = None
) -> dict:
    """运行单篇论文的完整测试"""
    if model_names is None:
        model_names = CHINA_MODELS

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
    all_means = [dr["mean"] for dr in dimension_results.values()]
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

    # 最高 std 维度
    if dimension_results:
        worst_dim = max(dimension_results.values(), key=lambda d: d["std"])
        result["overall"]["worst_dimension"] = worst_dim["dimension"]
        result["overall"]["worst_std"] = worst_dim["std"]

    print(f"\n总体统计：")
    print(f"  加权总分：{result['overall']['weighted_total']}")
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
                paper, framework, dimension_results, trigger_reason, review_model
            )
        else:
            result["gpt_review"] = {
                "triggered": False,
                "reason": "未达到触发条件"
            }
            print(f"\n未触发 GPT 复核：未达到触发条件")
    else:
        result["gpt_review"] = {
            "triggered": False,
            "reason": "用户禁用"
        }
        print(f"\n跳过 GPT 复核（用户禁用）")

    return result


# ============================================================================
# 批量测试
# ============================================================================

async def run_batch_test(
    output_dir: str,
    framework_path: str = DEFAULT_FRAMEWORK,
    enable_gpt_review: bool = True,
    review_model: str = DEFAULT_REVIEW_MODEL,
) -> dict:
    """批量测试预定义样本"""
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
            review_model=review_model,
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

    high_confidence_papers = sum(
        1 for r in all_results if r["overall"]["high_confidence_pct"] >= 50
    )

    summary["overall_statistics"] = {
        "avg_std_mean": round(statistics.mean(all_avg_stds), 1),
        "avg_std_median": round(statistics.median(all_avg_stds), 1),
        "max_std_mean": round(statistics.mean(all_max_stds), 1),
        "weighted_total_mean": round(statistics.mean(all_weighted_totals), 1),
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
        "--review-model",
        default=DEFAULT_REVIEW_MODEL,
        help=f"GPT 复核模型名称（默认：{DEFAULT_REVIEW_MODEL}，走 Zenmux）",
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
    enable_gpt_review = not args.no_gpt_review

    if args.batch:
        # 批量测试
        result = asyncio.run(
            run_batch_test(
                output_dir=args.output_dir,
                framework_path=args.framework,
                enable_gpt_review=enable_gpt_review,
                review_model=args.review_model,
            )
        )

        print(f"\n{'='*80}")
        print(f"批量测试完成")
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
                review_model=args.review_model,
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
        print(f"测试完成")
        print(f"{'='*80}")
        print(f"结果已保存：{output_path}")


if __name__ == "__main__":
    main()
