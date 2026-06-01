#!/usr/bin/env python3
"""Phase 1: 100 篇论文验证测试（4 模型 + 最严格聚合）

使用 4 个模型进行单次评测，同时输出 mean 和 strictest 两种聚合结果。
论文级并发 + 维度级并发，大幅缩短总耗时。
每 10 篇输出一次进展报告。

模型配置：deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus
聚合模式：both（同时计算 mean 和 strictest）
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test


async def evaluate_paper(
    index: int,
    total: int,
    paper_path: str,
    framework: str,
    models: list[str],
    output_path: Path,
    semaphore: asyncio.Semaphore,
    aggregation_mode: str = "both",
) -> dict | None:
    """评估单篇论文（带并发控制）"""
    paper_name = Path(paper_path).stem[:50]

    # 断点续传：跳过已完成的
    if output_path.exists():
        print(f"[{index}/{total}] {paper_name} → 跳过（已完成）")
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("overall", {})

    async with semaphore:
        print(f"[{index}/{total}] {paper_name} → 开始评估...")
        try:
            result = await run_convergence_test(
                framework_path=framework,
                paper_path=paper_path,
                model_names=models,
                aggregation_mode=aggregation_mode,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            overall = result.get("overall", {})

            # 根据聚合模式打印不同的信息
            if aggregation_mode == "both":
                score_mean = overall.get("aggregation_mean", {}).get("final_score")
                score_strictest = overall.get("aggregation_strictest", {}).get("final_score")
                max_std = overall.get("max_std", "?")
                gap = overall.get("score_gap", "?")
                print(f"[{index}/{total}] {paper_name} → mean={score_mean}, strictest={score_strictest}, gap={gap}, max_std={max_std}")
            elif aggregation_mode == "strictest":
                score = overall.get("aggregation_strictest", {}).get("final_score")
                print(f"[{index}/{total}] {paper_name} → strictest={score}")
            else:  # mean
                score = overall.get("final_score")
                max_std = overall.get("max_std", "?")
                print(f"[{index}/{total}] {paper_name} → final_score={score}, max_std={max_std}")

            return overall
        except Exception as e:
            print(f"[{index}/{total}] {paper_name} → 失败: {e}")
            return None


def track_metrics(output_dir: Path, batch_num: int, all_scores_mean: list,
                 all_scores_strictest: list, elapsed: float, total_papers: int,
                 std_over_8_count: int, critical_std_count: int):
    """记录当前批次指标到 JSONL 文件"""
    metrics = {
        "batch": batch_num,
        "completed_papers": total_papers,
        "timestamp": datetime.now().isoformat(),
        "mean_aggregation": {
            "overall_avg": round(sum(all_scores_mean) / len(all_scores_mean), 1) if all_scores_mean else None,
            "score_distribution": {
                "90_100": sum(1 for s in all_scores_mean if s >= 90),
                "80_90": sum(1 for s in all_scores_mean if 80 <= s < 90),
                "70_80": sum(1 for s in all_scores_mean if 70 <= s < 80),
                "below_70": sum(1 for s in all_scores_mean if s < 70)
            }
        },
        "strictest_aggregation": {
            "overall_avg": round(sum(all_scores_strictest) / len(all_scores_strictest), 1) if all_scores_strictest else None,
            "score_distribution": {
                "90_100": sum(1 for s in all_scores_strictest if s >= 90),
                "80_90": sum(1 for s in all_scores_strictest if 80 <= s < 90),
                "70_80": sum(1 for s in all_scores_strictest if 70 <= s < 80),
                "below_70": sum(1 for s in all_scores_strictest if s < 70)
            }
        },
        "std_over_8_count": std_over_8_count,
        "critical_std_count": critical_std_count,
        "avg_time_per_paper": round(elapsed / total_papers, 1),
        "elapsed_minutes": round(elapsed / 60, 1),
        "estimated_remaining_minutes": round((100 - total_papers) * (elapsed / total_papers) / 60, 1)
    }

    tracking_file = output_dir / "metrics-tracking.jsonl"
    with open(tracking_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + '\n')

    return metrics


async def main():
    parser = argparse.ArgumentParser(description="Phase 1: 100 篇论文验证测试（4 模型 + 最严格聚合）")
    parser.add_argument("--framework", default="configs/frameworks/law-v2.50.2-20260514.yaml")
    parser.add_argument("--models", default="deepseek-v4-pro,glm-5.1,kimi-k2.6,qwen3.6-plus")
    parser.add_argument("--output-dir", default="results/phase1-100-papers-strictest")
    parser.add_argument("--concurrency", type=int, default=5, help="论文级并发数（默认 5）")
    parser.add_argument(
        "--aggregation-mode",
        default="both",
        choices=["mean", "strictest", "both"],
        help="聚合模式：mean（均值），strictest（最严格），both（同时计算两种，推荐）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path("raw/phase1-100-papers/manifest.json")
    if not manifest_path.exists():
        print("错误：样本清单不存在")
        print("请先运行：python scripts/phase1_sample_selection.py")
        return 1

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    samples = manifest["samples"]
    model_names = args.models.split(",")

    print("=" * 60)
    print("Phase 1: 100 篇论文验证测试（4 模型 + 最严格聚合）")
    print("=" * 60)
    print(f"框架: {args.framework}")
    print(f"模型: {args.models}")
    print(f"聚合模式: {args.aggregation_mode}")
    print(f"样本数: {len(samples)} 篇（三大刊）")
    print(f"论文并发: {args.concurrency}")
    print(f"输出目录: {output_dir}")
    print("=" * 60 + "\n")

    start_time = time.time()
    paper_semaphore = asyncio.Semaphore(args.concurrency)

    # 并发评估所有论文
    tasks = []
    for i, paper in enumerate(samples, 1):
        out_path = output_dir / f"paper-{i:03d}.json"
        tasks.append(
            evaluate_paper(i, len(samples), paper, args.framework, model_names, out_path, paper_semaphore, args.aggregation_mode)
        )

    results = await asyncio.gather(*tasks)

    # 汇总结果
    elapsed = time.time() - start_time
    all_scores_mean = []
    all_scores_strictest = []
    std_over_8_count = 0
    critical_std_count = 0

    for overall in results:
        if overall:
            if args.aggregation_mode in ["mean", "both"]:
                score_mean = overall.get("aggregation_mean", {}).get("final_score")
                if score_mean is not None:
                    all_scores_mean.append(score_mean)

            if args.aggregation_mode in ["strictest", "both"]:
                score_strictest = overall.get("aggregation_strictest", {}).get("final_score")
                if score_strictest is not None:
                    all_scores_strictest.append(score_strictest)

            if overall.get("max_std", 0) > 8:
                std_over_8_count += 1
            if overall.get("max_std", 0) > 12:
                critical_std_count += 1

    total_papers = len(samples)

    # 最终报告
    print("\n" + "=" * 60)
    print("Phase 1 最终报告（100 篇论文，4 模型，双聚合模式）")
    print("=" * 60)
    print(f"模型配置：{args.models}")
    print(f"聚合模式：{args.aggregation_mode}")

    if args.aggregation_mode in ["mean", "both"] and all_scores_mean:
        print("\n--- Mean 聚合结果 ---")
        overall_avg_mean = sum(all_scores_mean) / len(all_scores_mean)
        print(f"整体均值: {overall_avg_mean:.1f} 分")
        print(f"分数分布：")
        print(f"   - 90-100 分：{sum(1 for s in all_scores_mean if s >= 90)} 篇")
        print(f"   - 80-90 分：{sum(1 for s in all_scores_mean if 80 <= s < 90)} 篇")
        print(f"   - 70-80 分：{sum(1 for s in all_scores_mean if 70 <= s < 80)} 篇")
        print(f"   - < 70 分：{sum(1 for s in all_scores_mean if s < 70)} 篇")

    if args.aggregation_mode in ["strictest", "both"] and all_scores_strictest:
        print("\n--- Strictest 聚合结果 ---")
        overall_avg_strictest = sum(all_scores_strictest) / len(all_scores_strictest)
        print(f"整体均值: {overall_avg_strictest:.1f} 分", end="")
        if all_scores_mean:
            gap = overall_avg_mean - overall_avg_strictest
            print(f"（比 mean 低 {gap:.1f} 分）")
        else:
            print()
        print(f"分数分布：")
        print(f"   - 90-100 分：{sum(1 for s in all_scores_strictest if s >= 90)} 篇")
        print(f"   - 80-90 分：{sum(1 for s in all_scores_strictest if 80 <= s < 90)} 篇")
        print(f"   - 70-80 分：{sum(1 for s in all_scores_strictest if 70 <= s < 80)} 篇")
        print(f"   - < 70 分：{sum(1 for s in all_scores_strictest if s < 70)} 篇")

        # 分层统计
        high_candidates = sum(1 for s in all_scores_strictest if s > 75)
        medium_candidates = sum(1 for s in all_scores_strictest if 65 <= s <= 75)
        boundary_candidates = sum(1 for s in all_scores_strictest if 60 <= s < 65)
        print(f"\n高分候选（strictest > 75）：{high_candidates} 篇")
        print(f"重点候选（strictest 65-75）：{medium_candidates} 篇")
        print(f"边界候选（strictest 60-65）：{boundary_candidates} 篇")

    # 可靠性统计
    std_over_8_ratio = std_over_8_count / (total_papers * 6) * 100 if total_papers > 0 else 0
    critical_std_ratio = critical_std_count / (total_papers * 6) * 100 if total_papers > 0 else 0
    print(f"\n--- 可靠性统计 ---")
    print(f"std > 8: {std_over_8_ratio:.1f}% (目标 <= 20%)")
    print(f"std > 12: {critical_std_ratio:.1f}% (目标 <= 5%)")

    print(f"\n总耗时: {elapsed/60:.1f} 分钟 ({elapsed/3600:.1f} 小时)")
    print(f"平均耗时: {elapsed/total_papers:.1f} 秒/篇")

    # 保存最终结果
    result = {
        "test_time": datetime.now().isoformat(),
        "framework": args.framework,
        "models": model_names,
        "aggregation_mode": args.aggregation_mode,
        "total_papers": total_papers,
        "concurrency": args.concurrency,
        "source": "三大刊（中国法学 40 + 法学研究 40 + 中国社会科学 20）",
        "metrics": {
            "std_over_8_ratio": round(std_over_8_ratio / 100, 3),
            "critical_std_ratio": round(critical_std_ratio / 100, 3),
        },
        "elapsed_seconds": round(elapsed, 1),
    }

    if all_scores_mean:
        result["all_scores_mean"] = all_scores_mean
        result["metrics"]["mean_aggregation"] = {
            "overall_avg": round(sum(all_scores_mean) / len(all_scores_mean), 1),
            "extreme_ratio": round((sum(1 for s in all_scores_mean if s < 70) + sum(1 for s in all_scores_mean if s > 95)) / len(all_scores_mean), 3),
        }

    if all_scores_strictest:
        result["all_scores_strictest"] = all_scores_strictest
        result["metrics"]["strictest_aggregation"] = {
            "overall_avg": round(sum(all_scores_strictest) / len(all_scores_strictest), 1),
            "high_candidates": sum(1 for s in all_scores_strictest if s > 75),
            "medium_candidates": sum(1 for s in all_scores_strictest if 65 <= s <= 75),
            "boundary_candidates": sum(1 for s in all_scores_strictest if 60 <= s < 65),
        }

    result_path = output_dir / f"phase1-result-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {result_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
