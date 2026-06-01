#!/usr/bin/env python3
"""分析第二轮交叉评审的分数分布"""

import json
from pathlib import Path
from collections import Counter

def main():
    results_file = Path(__file__).parent.parent / "results" / "cross-review-enhanced-analysis.json"

    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 提取所有论文的第二轮数据
    papers = []
    for paper_data in data["papers"]:
        paper_name = paper_data["paper"]
        dimensions = paper_data["dimensions"]

        # 计算第二轮六维平均分
        round2_scores = []
        round2_stds = []
        for dim_name, dim_data in dimensions.items():
            if "round2_mean" in dim_data:
                round2_scores.append(dim_data["round2_mean"])
                round2_stds.append(dim_data["round2_std"])

        if round2_scores:
            papers.append({
                "paper": paper_name,
                "round2_mean": sum(round2_scores) / len(round2_scores),
                "round2_avg_std": sum(round2_stds) / len(round2_stds)
            })

    # 按平均分降序排序
    papers.sort(key=lambda x: x["round2_mean"], reverse=True)

    # 统计数据
    scores = [p["round2_mean"] for p in papers]
    stds = [p["round2_avg_std"] for p in papers]

    print("=" * 100)
    print("第二轮交叉评审分数分布统计")
    print("=" * 100)
    print(f"\n总论文数: {len(papers)}")
    print(f"\n平均分统计:")
    print(f"  最高分: {max(scores):.2f}")
    print(f"  最低分: {min(scores):.2f}")
    print(f"  平均值: {sum(scores) / len(scores):.2f}")
    print(f"  中位数: {sorted(scores)[len(scores) // 2]:.2f}")

    print(f"\n标准差统计:")
    print(f"  最高: {max(stds):.2f}")
    print(f"  最低: {min(stds):.2f}")
    print(f"  平均: {sum(stds) / len(stds):.2f}")

    # 分数区间分布
    print(f"\n分数区间分布:")
    bins = [
        (90, 100, "90-100"),
        (85, 90, "85-90"),
        (80, 85, "80-85"),
        (75, 80, "75-80"),
        (70, 75, "70-75"),
        (0, 70, "<70")
    ]

    for low, high, label in bins:
        count = sum(1 for s in scores if low <= s < high)
        percentage = count / len(scores) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {label:>8}: {count:3d} 篇 ({percentage:5.1f}%) {bar}")

    # 标准差区间分布
    print(f"\n标准差区间分布:")
    std_bins = [
        (0, 3, "<3 (高一致性)"),
        (3, 5, "3-5 (中等一致性)"),
        (5, 8, "5-8 (低一致性)"),
        (8, 100, ">8 (分歧显著)")
    ]

    for low, high, label in std_bins:
        count = sum(1 for s in stds if low <= s < high)
        percentage = count / len(stds) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {label:>20}: {count:3d} 篇 ({percentage:5.1f}%) {bar}")

    # 输出完整排名
    print(f"\n" + "=" * 100)
    print("完整排名（1-100）")
    print("=" * 100)
    print(f"{'排名':<6} {'平均分':<10} {'平均标准差':<12} {'论文标题'}")
    print("-" * 100)

    for i, paper in enumerate(papers, 1):
        print(f"{i:<6} {paper['round2_mean']:<10.2f} {paper['round2_avg_std']:<12.2f} {paper['paper']}")

    print("=" * 100)

if __name__ == "__main__":
    main()
