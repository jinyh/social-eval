#!/usr/bin/env python3
"""单篇论文 Round 1 → Round 2 完整测试

随机选一篇论文，执行完整的两轮评审流程，验证脚本正确性。

用法：
    python scripts/test_single_paper_two_rounds.py \
        --paper "raw/phase1-100-papers/032_我国民事庭审阶段化构造再认识.pdf"
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

from scripts.run_convergence_test import run_convergence_test
from scripts.run_cross_review import (
    build_cross_review_prompt,
    evaluate_dimension_cross_review,
    A_GROUP,
    B_GROUP,
    _load_framework,
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file


MODELS = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
FRAMEWORK_PATH = 'configs/frameworks/law-v2.55-cross-review.yaml'


async def run_test(paper_path: str, output_dir: Path):
    paper_name = Path(paper_path).stem
    print(f"{'='*80}")
    print(f"单篇完整测试：{paper_name}")
    print(f"框架：{FRAMEWORK_PATH}")
    print(f"模型：{', '.join(MODELS)}")
    print(f"{'='*80}\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    # ========== Round 1 ==========
    print("=" * 40)
    print("Round 1: 多模型并发评审")
    print("=" * 40)

    start_time = time.time()
    round1_result = await run_convergence_test(
        framework_path=FRAMEWORK_PATH,
        paper_path=paper_path,
        model_names=MODELS,
        aggregation_mode="both",
    )
    round1_elapsed = time.time() - start_time

    # 保存 Round 1 结果
    round1_path = output_dir / "round1.json"
    round1_path.write_text(
        json.dumps(round1_result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 打印 Round 1 摘要
    overall = round1_result.get("overall", {})
    print(f"\n--- Round 1 结果 ---")
    print(f"  Mean 总分: {overall.get('aggregation_mean', {}).get('final_score')}")
    print(f"  Strictest 总分: {overall.get('aggregation_strictest', {}).get('final_score')}")
    print(f"  平均 std: {overall.get('avg_std')}")
    print(f"  最大 std: {overall.get('max_std')}")
    print(f"  高置信度比例: {overall.get('high_confidence_pct')}%")
    print(f"  耗时: {round1_elapsed:.1f}s\n")

    # 打印各维度详情
    print("  各维度评分:")
    for dim_key, dim_data in round1_result.get("dimensions", {}).items():
        scores = dim_data.get("model_scores", {})
        scores_str = ", ".join(f"{k}={v}" for k, v in scores.items())
        print(f"    {dim_data.get('name_zh', dim_key)}: {scores_str} | mean={dim_data.get('mean')} | std={dim_data.get('std')}")

    # ========== Round 2 ==========
    print(f"\n{'='*40}")
    print("Round 2: 交叉评审")
    print("=" * 40)

    start_time = time.time()

    # 加载框架和 providers
    framework = _load_framework(FRAMEWORK_PATH)
    providers_list = create_providers(MODELS)
    providers = {p.model_name: p for p in providers_list}

    # 加载论文
    paper = process_file(paper_path)

    # 并发控制
    semaphore = asyncio.Semaphore(10)

    # 对每个维度执行交叉评审
    round2_dimensions = {}
    for dim in framework.dimensions:
        round1_dim = round1_result.get("dimensions", {}).get(dim.key)
        if not round1_dim:
            continue

        dim_result = await evaluate_dimension_cross_review(
            dimension_key=dim.key,
            dimension_name=dim.name_zh,
            round1_dim_result=round1_dim,
            paper=paper,
            providers=providers,
            semaphore=semaphore,
        )
        round2_dimensions[dim.key] = dim_result

        # 打印进度
        r1_std = dim_result['round1_std']
        r2_std = dim_result['round2_std']
        improvement = dim_result['convergence_improvement']
        print(f"  {dim.name_zh}: std {r1_std} → {r2_std} (改善 {improvement:+.1f})")

    round2_elapsed = time.time() - start_time

    # 构建 Round 2 完整结果
    round2_result = {
        "paper": paper_path,
        "framework": FRAMEWORK_PATH,
        "models": MODELS,
        "dimensions": round2_dimensions,
        "overall": {},
    }

    # 计算 Round 2 总体统计
    all_round2_stds = [d['round2_std'] for d in round2_dimensions.values()]
    all_round1_stds = [d['round1_std'] for d in round2_dimensions.values()]

    if all_round2_stds:
        round2_result["overall"] = {
            "round1_avg_std": round(statistics.mean(all_round1_stds), 2),
            "round2_avg_std": round(statistics.mean(all_round2_stds), 2),
            "std_improvement": round(
                statistics.mean(all_round1_stds) - statistics.mean(all_round2_stds), 2
            ),
            "round1_max_std": round(max(all_round1_stds), 2),
            "round2_max_std": round(max(all_round2_stds), 2),
            "dimensions_converged": sum(1 for s in all_round2_stds if s <= 8),
            "total_dimensions": len(all_round2_stds),
        }

    # 保存 Round 2 结果
    round2_path = output_dir / "round2.json"
    round2_path.write_text(
        json.dumps(round2_result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ========== 最终报告 ==========
    print(f"\n{'='*40}")
    print("最终报告")
    print("=" * 40)

    r2_overall = round2_result["overall"]
    print(f"  Round 1 平均 std: {r2_overall.get('round1_avg_std')}")
    print(f"  Round 2 平均 std: {r2_overall.get('round2_avg_std')}")
    print(f"  std 改善: {r2_overall.get('std_improvement')}")
    print(f"  Round 1 最大 std: {r2_overall.get('round1_max_std')}")
    print(f"  Round 2 最大 std: {r2_overall.get('round2_max_std')}")
    print(f"  收敛维度 (std≤8): {r2_overall.get('dimensions_converged')}/{r2_overall.get('total_dimensions')}")
    print(f"  Round 2 耗时: {round2_elapsed:.1f}s")
    print(f"  总耗时: {round1_elapsed + round2_elapsed:.1f}s")

    # 打印各维度对比
    print(f"\n  各维度 Round 1 → Round 2 对比:")
    for dim_key, dim_data in round2_dimensions.items():
        r1_scores = dim_data.get('round1_scores', {})
        r2_scores = dim_data.get('round2_scores', {})
        print(f"    {dim_data['name_zh']}:")
        for model in MODELS:
            r1 = r1_scores.get(model, '?')
            r2 = r2_scores.get(model, '?')
            if isinstance(r1, (int, float)) and isinstance(r2, (int, float)):
                diff = r2 - r1
                print(f"      {model}: {r1} → {r2} ({diff:+.0f})")
            else:
                print(f"      {model}: {r1} → {r2}")

    print(f"\n结果已保存到: {output_dir}")
    print(f"  Round 1: {round1_path}")
    print(f"  Round 2: {round2_path}")


def main():
    parser = argparse.ArgumentParser(description="单篇论文 Round 1 → Round 2 完整测试")
    parser.add_argument(
        "--paper",
        default="raw/phase1-100-papers/032_我国民事庭审阶段化构造再认识.pdf",
        help="论文 PDF 路径",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录（默认 results/single-paper-test-<timestamp>）",
    )
    args = parser.parse_args()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path(f"results/single-paper-test-{timestamp}")

    asyncio.run(run_test(args.paper, output_dir))


if __name__ == "__main__":
    main()
