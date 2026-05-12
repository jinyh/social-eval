"""测试 Kimi K-2.6 的评分表现

对比 Kimi K-2.6 与 GLM-5.1/Qwen3.6-Plus 的评分差异

用法：
    python scripts/test_kimi_k26.py \
        --paper raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf \
        --framework configs/frameworks/law-v2.42-20260507.yaml
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt
from src.evaluation.providers.dashscope_provider import DashScopeProvider
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework


async def evaluate_single_run(provider, dimension, paper) -> tuple[dict | None, str | None, float]:
    """单次评价"""
    prompt = build_prompt(dimension, paper)
    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
        elapsed = time.time() - start
        return raw, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return None, str(e), elapsed


async def test_kimi_k26(paper_path: str, framework_path: str):
    """测试 Kimi K-2.6 的评分表现"""

    print(f"=== Kimi K-2.6 评分测试 ===")
    print(f"论文: {paper_path}")
    print(f"框架: {framework_path}")
    print()

    # 加载框架和论文
    framework = load_framework(framework_path)
    paper = process_file(paper_path)

    # 创建 Kimi K-2.6 provider
    print("创建 Kimi K-2.6 provider...")
    provider = DashScopeProvider("kimi-k2.6")

    # 评价所有维度
    results = {}

    print(f"\n{'='*80}")
    print("开始评价")
    print(f"{'='*80}\n")

    for dimension in framework.dimensions:
        print(f"  评价维度: {dimension.name_zh}...", end=" ", flush=True)

        raw, error, elapsed = await evaluate_single_run(provider, dimension, paper)

        if error:
            print(f"❌ 错误: {error}")
            results[dimension.key] = {
                "error": error,
                "elapsed": elapsed
            }
        elif raw and isinstance(raw, dict) and "score" in raw:
            score = int(raw["score"])
            print(f"✓ {score} 分 ({elapsed:.1f}s)")
            results[dimension.key] = {
                "score": score,
                "raw": raw,
                "elapsed": elapsed
            }
        else:
            print(f"❌ 无效输出")
            results[dimension.key] = {
                "error": "Invalid output",
                "elapsed": elapsed
            }

    # 提取分数
    scores = []
    for dim in framework.dimensions:
        if dim.key in results and "score" in results[dim.key]:
            scores.append(results[dim.key]["score"])

    # 对比分析
    print(f"\n{'='*80}")
    print("与 GLM-5.1/Qwen3.6-Plus 的对比")
    print(f"{'='*80}\n")

    # 参考分数（来自之前的测试）
    reference_scores = {
        "problem_originality": 88,
        "literature_insight": 90,
        "analytical_framework": 90,
        "logical_coherence": 88,
        "conclusion_consensus": 88,
        "forward_extension": 50
    }

    print(f"{'维度':<15s} {'GLM/Qwen':>10s} {'Kimi K-2.6':>12s} {'差异':>8s}")
    print("-" * 55)

    diffs = []
    for dimension in framework.dimensions:
        ref_score = reference_scores.get(dimension.key, 0)

        if dimension.key in results and "score" in results[dimension.key]:
            score = results[dimension.key]["score"]
            diff = score - ref_score
            diffs.append(diff)
            print(f"{dimension.name_zh:<15s} {ref_score:>10d} {score:>12d} {diff:>8d}")
        else:
            print(f"{dimension.name_zh:<15s} {ref_score:>10d} {'N/A':>12s} {'N/A':>8s}")

    # 统计数据
    if scores and diffs:
        print(f"\n{'='*80}")
        print("统计数据")
        print(f"{'='*80}\n")

        avg_score = statistics.mean(scores)
        avg_diff = statistics.mean(diffs)
        max_pos_diff = max(diffs)
        max_neg_diff = min(diffs)

        print(f"Kimi K-2.6 平均分: {avg_score:.1f}")
        print(f"GLM/Qwen 平均分: {statistics.mean(reference_scores.values()):.1f}")
        print(f"平均差异: {avg_diff:+.1f}")
        print(f"最大正差: {max_pos_diff:+d}")
        print(f"最大负差: {max_neg_diff:+d}")

        # 评价
        print(f"\n{'='*80}")
        print("评价")
        print(f"{'='*80}\n")

        if abs(avg_diff) < 5:
            rating = "✓ 优秀 - 与 GLM/Qwen 高度一致"
        elif abs(avg_diff) < 10:
            rating = "○ 良好 - 差异可接受"
        elif abs(avg_diff) < 20:
            rating = "△ 一般 - 差异较大"
        else:
            rating = "✗ 较差 - 差异过大，不推荐使用"

        print(f"评价: {rating}")

        # 与 DeepSeek 对比
        deepseek_avg_diff = -25.3
        print(f"\n对比 DeepSeek-v4-pro:")
        print(f"  DeepSeek 平均差异: {deepseek_avg_diff:+.1f}")
        print(f"  Kimi K-2.6 平均差异: {avg_diff:+.1f}")

        if abs(avg_diff) < abs(deepseek_avg_diff):
            print(f"  结论: Kimi K-2.6 比 DeepSeek 更接近 GLM/Qwen")
        else:
            print(f"  结论: Kimi K-2.6 与 DeepSeek 类似，偏差较大")

    # 保存结果
    output_path = f"results/kimi-k26-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_info": {
                "paper": paper_path,
                "framework": framework_path,
                "model": "kimi-k2.6",
                "timestamp": datetime.now().isoformat()
            },
            "results": results,
            "reference_scores": reference_scores,
            "statistics": {
                "avg_score": avg_score if scores else None,
                "avg_diff": avg_diff if diffs else None,
                "max_pos_diff": max_pos_diff if diffs else None,
                "max_neg_diff": max_neg_diff if diffs else None
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Kimi K-2.6 评分测试")
    parser.add_argument("--paper", required=True, help="论文路径")
    parser.add_argument("--framework", required=True, help="框架配置路径")

    args = parser.parse_args()

    asyncio.run(test_kimi_k26(args.paper, args.framework))


if __name__ == "__main__":
    main()
