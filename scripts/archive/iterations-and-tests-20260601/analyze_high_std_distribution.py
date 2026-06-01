#!/usr/bin/env python3
"""分析标准差大于8分的论文的平均分分布"""

import json
from pathlib import Path

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

    # 筛选标准差 > 8 的论文
    high_std_papers = [p for p in papers if p["round2_avg_std"] > 8]
    high_std_papers.sort(key=lambda x: x["round2_mean"], reverse=True)

    # 统计数据
    scores = [p["round2_mean"] for p in high_std_papers]
    stds = [p["round2_avg_std"] for p in high_std_papers]

    print("=" * 100)
    print("标准差 > 8 的论文分数分布统计")
    print("=" * 100)
    print(f"\n总论文数: {len(high_std_papers)} 篇（占总数 {len(high_std_papers)/len(papers)*100:.1f}%）")

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
        (85, 100, "85-100"),
        (80, 85, "80-85"),
        (75, 80, "75-80"),
        (70, 75, "70-75"),
        (65, 70, "65-70"),
        (60, 65, "60-65"),
        (0, 60, "<60")
    ]

    for low, high, label in bins:
        count = sum(1 for s in scores if low <= s < high)
        percentage = count / len(scores) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {label:>8}: {count:3d} 篇 ({percentage:5.1f}%) {bar}")

    # 标准差区间分布
    print(f"\n标准差区间分布:")
    std_bins = [
        (8, 9, "8-9"),
        (9, 10, "9-10"),
        (10, 11, "10-11"),
        (11, 12, "11-12"),
        (12, 15, "12-15"),
        (15, 100, ">15")
    ]

    for low, high, label in std_bins:
        count = sum(1 for s in stds if low <= s < high)
        percentage = count / len(stds) * 100
        bar = "█" * int(percentage / 2)
        print(f"  {label:>8}: {count:3d} 篇 ({percentage:5.1f}%) {bar}")

    # 输出完整列表
    print(f"\n" + "=" * 100)
    print(f"标准差 > 8 的论文完整列表（共 {len(high_std_papers)} 篇，按平均分降序）")
    print("=" * 100)
    print(f"{'排名':<6} {'平均分':<10} {'标准差':<10} {'论文标题'}")
    print("-" * 100)

    for i, paper in enumerate(high_std_papers, 1):
        print(f"{i:<6} {paper['round2_mean']:<10.2f} {paper['round2_avg_std']:<10.2f} {paper['paper']}")

    print("=" * 100)

    # 对比分析
    all_scores = [p["round2_mean"] for p in papers]
    low_std_papers = [p for p in papers if p["round2_avg_std"] <= 8]
    low_std_scores = [p["round2_mean"] for p in low_std_papers]

    print(f"\n对比分析:")
    print(f"  全部论文平均分: {sum(all_scores) / len(all_scores):.2f}")
    print(f"  标准差 ≤ 8 的论文平均分: {sum(low_std_scores) / len(low_std_scores):.2f}")
    print(f"  标准差 > 8 的论文平均分: {sum(scores) / len(scores):.2f}")
    print(f"  差值: {sum(low_std_scores) / len(low_std_scores) - sum(scores) / len(scores):.2f} 分")

if __name__ == "__main__":
    main()
