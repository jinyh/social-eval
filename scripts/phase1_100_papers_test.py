#!/usr/bin/env python3
"""Phase 1: 100 篇论文验证测试（三大刊）
论文级并发 + 维度级并发，大幅缩短总耗时。
每 10 篇输出一次进展报告。
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
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            overall = result.get("overall", {})
            score = overall.get("final_score")
            max_std = overall.get("max_std", "?")
            print(f"[{index}/{total}] {paper_name} → final_score={score}, max_std={max_std}")
            return overall
        except Exception as e:
            print(f"[{index}/{total}] {paper_name} → 失败: {e}")
            return None


def track_metrics(output_dir: Path, batch_num: int, all_scores: list,
                 elapsed: float, total_papers: int,
                 std_over_8_count: int, critical_std_count: int):
    """记录当前批次指标到 JSONL 文件"""
    score_90_100 = sum(1 for s in all_scores if s >= 90)
    score_80_90 = sum(1 for s in all_scores if 80 <= s < 90)
    score_70_80 = sum(1 for s in all_scores if 70 <= s < 80)
    score_below_70 = sum(1 for s in all_scores if s < 70)

    metrics = {
        "batch": batch_num,
        "completed_papers": total_papers,
        "timestamp": datetime.now().isoformat(),
        "overall_avg": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        "score_distribution": {
            "90_100": score_90_100,
            "80_90": score_80_90,
            "70_80": score_70_80,
            "below_70": score_below_70
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
    parser = argparse.ArgumentParser(description="Phase 1: 100 篇论文验证测试（三大刊）")
    parser.add_argument("--framework", default="configs/frameworks/law-v2.50.2-20260514.yaml")
    parser.add_argument("--models", default="qwen3.6-plus,glm-5.1")
    parser.add_argument("--output-dir", default="results/phase1-100-papers")
    parser.add_argument("--concurrency", type=int, default=5, help="论文级并发数（默认 5）")
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
    print("Phase 1: 100 篇论文验证测试（三大刊）")
    print("=" * 60)
    print(f"框架: {args.framework}")
    print(f"模型: {args.models}")
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
            evaluate_paper(i, len(samples), paper, args.framework, model_names, out_path, paper_semaphore)
        )

    results = await asyncio.gather(*tasks)

    # 汇总结果
    elapsed = time.time() - start_time
    all_scores = []
    std_over_8_count = 0
    critical_std_count = 0

    for overall in results:
        if overall and overall.get("final_score") is not None:
            all_scores.append(overall["final_score"])
            if overall.get("max_std", 0) > 8:
                std_over_8_count += 1
            if overall.get("max_std", 0) > 12:
                critical_std_count += 1

    total_papers = len(samples)

    # 最终报告
    print("\n" + "=" * 60)
    print("Phase 1 最终报告（100 篇）")
    print("=" * 60)

    if all_scores:
        overall_avg = sum(all_scores) / len(all_scores)
        extreme_low = sum(1 for s in all_scores if s < 70)
        extreme_high = sum(1 for s in all_scores if s > 95)
        extreme_ratio = (extreme_low + extreme_high) / len(all_scores) * 100

        print(f"整体均值: {overall_avg:.1f} (目标 75-85)")
        print(f"分数分布：")
        print(f"   - 90-100 分：{sum(1 for s in all_scores if s >= 90)} 篇")
        print(f"   - 80-90 分：{sum(1 for s in all_scores if 80 <= s < 90)} 篇")
        print(f"   - 70-80 分：{sum(1 for s in all_scores if 70 <= s < 80)} 篇")
        print(f"   - < 70 分：{sum(1 for s in all_scores if s < 70)} 篇")
        print(f"极端值比例: {extreme_ratio:.1f}% (目标 < 10%)")
    else:
        overall_avg = 0
        extreme_ratio = 0

    std_over_8_ratio = std_over_8_count / (total_papers * 6) * 100 if total_papers > 0 else 0
    critical_std_ratio = critical_std_count / (total_papers * 6) * 100 if total_papers > 0 else 0
    print(f"std > 8: {std_over_8_ratio:.1f}% (目标 <= 20%)")
    print(f"std > 12: {critical_std_ratio:.1f}% (目标 <= 5%)")

    print(f"总耗时: {elapsed/60:.1f} 分钟 ({elapsed/3600:.1f} 小时)")
    print(f"平均耗时: {elapsed/total_papers:.1f} 秒/篇")

    # 保存最终结果
    result = {
        "test_time": datetime.now().isoformat(),
        "framework": args.framework,
        "models": model_names,
        "total_papers": total_papers,
        "concurrency": args.concurrency,
        "source": "三大刊（中国法学 40 + 法学研究 40 + 中国社会科学 20）",
        "all_scores": all_scores,
        "metrics": {
            "overall_avg": round(overall_avg, 1) if all_scores else None,
            "extreme_ratio": round(extreme_ratio / 100, 3) if all_scores else None,
            "std_over_8_ratio": round(std_over_8_ratio / 100, 3),
            "critical_std_ratio": round(critical_std_ratio / 100, 3),
        },
        "elapsed_seconds": round(elapsed, 1),
    }

    result_path = output_dir / f"phase1-result-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {result_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
