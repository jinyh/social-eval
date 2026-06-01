#!/usr/bin/env python3
"""分析 100 篇论文的最严格聚合结果

生成对比报告：
- 分数分布对比（mean vs strictest）
- 高分论文清单
- 分数差异分析
- 模型贡献分析（哪个模型最常成为"最严格模型"）
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def load_results(output_dir: Path) -> list[dict]:
    """加载所有论文的评测结果"""
    results = []
    for json_file in sorted(output_dir.glob("paper-*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                results.append({
                    "paper": Path(data["paper"]).stem,
                    "paper_path": data["paper"],
                    "overall": data["overall"],
                    "dimensions": data["dimensions"],
                })
        except Exception as e:
            print(f"警告：无法加载 {json_file}: {e}")
    return results


def analyze_score_distribution(results: list[dict], mode: str) -> dict:
    """分析分数分布"""
    if mode == "mean":
        scores = [r["overall"]["aggregation_mean"]["final_score"] for r in results]
    else:  # strictest
        scores = [r["overall"]["aggregation_strictest"]["final_score"] for r in results]

    return {
        "count": len(scores),
        "mean": sum(scores) / len(scores) if scores else 0,
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "distribution": {
            "90_100": sum(1 for s in scores if s >= 90),
            "80_90": sum(1 for s in scores if 80 <= s < 90),
            "70_80": sum(1 for s in scores if 70 <= s < 80),
            "60_70": sum(1 for s in scores if 60 <= s < 70),
            "below_60": sum(1 for s in scores if s < 60),
        },
        "scores": scores,
    }


def analyze_model_contribution(results: list[dict]) -> dict:
    """分析各模型作为"最严格模型"的频率"""
    model_counts = Counter()
    total_dimensions = 0

    for result in results:
        for dim_key, dim_data in result["dimensions"].items():
            if "strictest_model" in dim_data:
                model_counts[dim_data["strictest_model"]] += 1
                total_dimensions += 1

    return {
        "total_dimensions": total_dimensions,
        "model_counts": dict(model_counts),
        "model_percentages": {
            model: round(count / total_dimensions * 100, 1)
            for model, count in model_counts.items()
        } if total_dimensions > 0 else {},
    }


def generate_high_score_list(results: list[dict], threshold: float = 75.0) -> list[dict]:
    """生成高分论文清单（按 strictest 分数排序）"""
    papers = []
    for result in results:
        score_strictest = result["overall"]["aggregation_strictest"]["final_score"]
        if score_strictest > threshold:
            papers.append({
                "paper": result["paper"],
                "score_strictest": score_strictest,
                "score_mean": result["overall"]["aggregation_mean"]["final_score"],
                "score_gap": result["overall"]["score_gap"],
                "max_std": result["overall"]["max_std"],
            })

    # 按 strictest 分数降序排序
    papers.sort(key=lambda x: x["score_strictest"], reverse=True)
    return papers


def analyze_score_gaps(results: list[dict]) -> dict:
    """分析 mean 和 strictest 的分数差异"""
    gaps = [r["overall"]["score_gap"] for r in results]

    return {
        "mean_gap": sum(gaps) / len(gaps) if gaps else 0,
        "min_gap": min(gaps) if gaps else 0,
        "max_gap": max(gaps) if gaps else 0,
        "gap_distribution": {
            "0_2": sum(1 for g in gaps if 0 <= g < 2),
            "2_4": sum(1 for g in gaps if 2 <= g < 4),
            "4_6": sum(1 for g in gaps if 4 <= g < 6),
            "6_8": sum(1 for g in gaps if 6 <= g < 8),
            "8_plus": sum(1 for g in gaps if g >= 8),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="分析 100 篇论文的最严格聚合结果")
    parser.add_argument("--input-dir", default="results/phase1-100-papers-strictest")
    parser.add_argument("--output-csv", default="results/phase1-100-papers-strictest/ranking.csv")
    parser.add_argument("--threshold", type=float, default=75.0, help="高分候选阈值（默认 75）")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"错误：输入目录不存在: {input_dir}")
        return 1

    print("=" * 60)
    print("分析 100 篇论文的最严格聚合结果")
    print("=" * 60)
    print(f"输入目录: {input_dir}")
    print(f"高分阈值: {args.threshold}")
    print("=" * 60 + "\n")

    # 加载结果
    print("加载评测结果...")
    results = load_results(input_dir)
    print(f"成功加载 {len(results)} 篇论文的结果\n")

    if not results:
        print("错误：没有找到有效的评测结果")
        return 1

    # 分析分数分布
    print("--- Mean 聚合分数分布 ---")
    mean_dist = analyze_score_distribution(results, "mean")
    print(f"平均分: {mean_dist['mean']:.1f}")
    print(f"范围: {mean_dist['min']:.1f} ~ {mean_dist['max']:.1f}")
    print(f"分布:")
    for range_name, count in mean_dist["distribution"].items():
        print(f"  {range_name}: {count} 篇")

    print("\n--- Strictest 聚合分数分布 ---")
    strictest_dist = analyze_score_distribution(results, "strictest")
    print(f"平均分: {strictest_dist['mean']:.1f}")
    print(f"范围: {strictest_dist['min']:.1f} ~ {strictest_dist['max']:.1f}")
    print(f"分布:")
    for range_name, count in strictest_dist["distribution"].items():
        print(f"  {range_name}: {count} 篇")

    # 分析分数差异
    print("\n--- 分数差异分析（mean - strictest）---")
    gap_analysis = analyze_score_gaps(results)
    print(f"平均差距: {gap_analysis['mean_gap']:.1f} 分")
    print(f"范围: {gap_analysis['min_gap']:.1f} ~ {gap_analysis['max_gap']:.1f} 分")
    print(f"差距分布:")
    for range_name, count in gap_analysis["gap_distribution"].items():
        print(f"  {range_name} 分: {count} 篇")

    # 模型贡献分析
    print('\n--- 模型贡献分析（最常成为"最严格模型"）---')
    model_contrib = analyze_model_contribution(results)
    print(f"总维度数: {model_contrib['total_dimensions']}")
    for model, percentage in sorted(
        model_contrib["model_percentages"].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        count = model_contrib["model_counts"][model]
        print(f"  {model}: {percentage}% ({count}/{model_contrib['total_dimensions']} 维度)")

    # 高分论文清单
    print(f"\n--- 高分论文清单（strictest > {args.threshold}）---")
    high_score_papers = generate_high_score_list(results, args.threshold)
    print(f"共 {len(high_score_papers)} 篇\n")

    if high_score_papers:
        print("Top 10:")
        for i, paper in enumerate(high_score_papers[:10], 1):
            print(f"  {i}. {paper['paper'][:60]}")
            print(f"     strictest={paper['score_strictest']:.1f}, mean={paper['score_mean']:.1f}, gap={paper['score_gap']:.1f}, max_std={paper['max_std']:.1f}")

    # 导出 CSV
    print(f"\n导出排名表到 CSV...")
    df_data = []
    for i, result in enumerate(results, 1):
        df_data.append({
            "排名": i,
            "论文": result["paper"],
            "strictest_分数": result["overall"]["aggregation_strictest"]["final_score"],
            "mean_分数": result["overall"]["aggregation_mean"]["final_score"],
            "分数差距": result["overall"]["score_gap"],
            "最大_std": result["overall"]["max_std"],
            "高置信度比例": result["overall"]["high_confidence_pct"],
        })

    df = pd.DataFrame(df_data)
    df = df.sort_values("strictest_分数", ascending=False).reset_index(drop=True)
    df["排名"] = range(1, len(df) + 1)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"已保存到: {output_csv}")

    # 保存分析报告
    report = {
        "total_papers": len(results),
        "threshold": args.threshold,
        "mean_distribution": mean_dist,
        "strictest_distribution": strictest_dist,
        "gap_analysis": gap_analysis,
        "model_contribution": model_contrib,
        "high_score_count": len(high_score_papers),
    }

    report_path = input_dir / "analysis-report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"分析报告已保存到: {report_path}")

    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
