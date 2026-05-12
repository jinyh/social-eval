"""GPT-5.4 稳定性测试脚本

对同一篇论文运行多次 GPT-5.4 评价，观察标准差。

用法：
    python scripts/test_gpt54_stability.py \
        --paper raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf \
        --framework configs/frameworks/law-v2.42-20260507.yaml \
        --runs 3
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

from src.evaluation.prompt_builder import build_prompt
from src.evaluation.providers.factory import create_providers
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


async def test_stability(paper_path: str, framework_path: str, runs: int = 3):
    """测试 GPT-5.4 的稳定性"""

    print(f"=== GPT-5.4 稳定性测试 ===")
    print(f"论文: {paper_path}")
    print(f"框架: {framework_path}")
    print(f"测试次数: {runs}")
    print()

    # 加载框架和论文
    framework = load_framework(framework_path)
    paper = process_file(paper_path)

    # 创建 GPT-5.4 provider
    providers = create_providers(["gpt-5.4"])
    if not providers:
        raise ValueError("无法创建 gpt-5.4 provider")
    provider = providers[0]

    # 存储所有运行的结果
    all_results = {dim.key: [] for dim in framework.dimensions}

    # 运行多次评价
    for run_idx in range(runs):
        print(f"\n--- 第 {run_idx + 1}/{runs} 次评价 ---")

        for dimension in framework.dimensions:
            print(f"  评价维度: {dimension.name_zh}...", end=" ", flush=True)

            raw, error, elapsed = await evaluate_single_run(provider, dimension, paper)

            if error:
                print(f"❌ 错误: {error}")
                all_results[dimension.key].append(None)
            elif raw and isinstance(raw, dict) and "score" in raw:
                score = int(raw["score"])
                print(f"✓ {score} 分 ({elapsed:.1f}s)")
                all_results[dimension.key].append({
                    "score": score,
                    "raw": raw,
                    "elapsed": elapsed
                })
            else:
                print(f"❌ 无效输出")
                all_results[dimension.key].append(None)

    # 计算统计数据
    print("\n=== 标准差分析 ===")
    stats = {}

    for dimension in framework.dimensions:
        results = [r for r in all_results[dimension.key] if r is not None]
        if len(results) < 2:
            print(f"{dimension.name_zh:12s}: 数据不足")
            continue

        scores = [r["score"] for r in results]
        mean = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0

        stats[dimension.key] = {
            "name_zh": dimension.name_zh,
            "scores": scores,
            "mean": mean,
            "std": std,
            "runs": len(scores)
        }

        print(f"{dimension.name_zh:12s}: 分数={scores}, 均值={mean:.1f}, 标准差={std:.1f}")

    # 计算整体平均标准差
    if stats:
        avg_std = statistics.mean([s["std"] for s in stats.values()])
        max_std = max([s["std"] for s in stats.values()])
        print(f"\n整体平均标准差: {avg_std:.1f}")
        print(f"最大标准差: {max_std:.1f}")

    # 保存结果
    output_path = f"results/gpt54-stability-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_info": {
                "paper": paper_path,
                "framework": framework_path,
                "model": "gpt-5.4",
                "runs": runs,
                "timestamp": datetime.now().isoformat()
            },
            "statistics": stats,
            "raw_results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="GPT-5.4 稳定性测试")
    parser.add_argument("--paper", required=True, help="论文路径")
    parser.add_argument("--framework", required=True, help="框架配置路径")
    parser.add_argument("--runs", type=int, default=3, help="测试次数（默认3次）")

    args = parser.parse_args()

    asyncio.run(test_stability(args.paper, args.framework, args.runs))


if __name__ == "__main__":
    main()
