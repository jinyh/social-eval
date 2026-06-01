#!/usr/bin/env python3
"""分析80分以上论文的标准差分布"""

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

    # 筛选 80 分以上的论文
    high_score_papers = [p for p in papers if p["round2_mean"] >= 80]
    high_score_papers.sort(key=lambda x: x["round2_mean"], reverse=True)

    # 统计数据
    scores = [p["round2_mean"] for p in high_score_papers]
    stds = [p["round2_avg_std"] for p in high_score_papers]

    print("=" * 100)
    print("80 分以上论文的标准差分布统计")
    print("=" * 100)
    print(f"\n总论文数: {len(high_score_papers)} 篇（占总数 {len(high_score_papers)/len(papers)*100:.1f}%）")

    print(f"\n平均分统计:")
    print(f"  最高分: {max(scores):.2f}")
    print(f"  最低分: {min(scores):.2f}")
    print(f"  平均值: {sum(scores) / len(scores):.2f}")
    print(f"  中位数: {sorted(scores)[len(scores) // 2]:.2f}")

    print(f"\n标准差统计:")
    print(f"  最高: {max(stds):.2f}")
    print(f"  最低: {min(stds):.2f}")
    print(f"  平均: {sum(stds) / len(stds):.2f}")
    print(f"  中位数: {sorted(stds)[len(stds) // 2]:.2f}")

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

    # 按标准差分组
    high_consistency = [p for p in high_score_papers if p["round2_avg_std"] < 3]
    medium_consistency = [p for p in high_score_papers if 3 <= p["round2_avg_std"] < 5]
    low_consistency = [p for p in high_score_papers if 5 <= p["round2_avg_std"] < 8]
    high_divergence = [p for p in high_score_papers if p["round2_avg_std"] >= 8]

    # 输出完整列表
    print(f"\n" + "=" * 100)
    print(f"80 分以上论文完整列表（共 {len(high_score_papers)} 篇，按平均分降序）")
    print("=" * 100)
    print(f"{'排名':<6} {'平均分':<10} {'标准差':<10} {'一致性':<15} {'论文标题'}")
    print("-" * 100)

    for i, paper in enumerate(high_score_papers, 1):
        std = paper['round2_avg_std']
        if std < 3:
            consistency = "高一致性"
        elif std < 5:
            consistency = "中等一致性"
        elif std < 8:
            consistency = "低一致性"
        else:
            consistency = "分歧显著"

        print(f"{i:<6} {paper['round2_mean']:<10.2f} {paper['round2_avg_std']:<10.2f} {consistency:<15} {paper['paper']}")

    print("=" * 100)

    # 分组统计
    print(f"\n分组详细统计:")
    print(f"\n1. 高一致性（std < 3）：{len(high_consistency)} 篇")
    if high_consistency:
        for p in high_consistency:
            print(f"   - {p['paper']} ({p['round2_mean']:.2f}, std {p['round2_avg_std']:.2f})")

    print(f"\n2. 中等一致性（3 ≤ std < 5）：{len(medium_consistency)} 篇")
    if medium_consistency:
        for p in medium_consistency:
            print(f"   - {p['paper']} ({p['round2_mean']:.2f}, std {p['round2_avg_std']:.2f})")

    print(f"\n3. 低一致性（5 ≤ std < 8）：{len(low_consistency)} 篇")
    if low_consistency:
        for p in low_consistency:
            print(f"   - {p['paper']} ({p['round2_mean']:.2f}, std {p['round2_avg_std']:.2f})")

    print(f"\n4. 分歧显著（std ≥ 8）：{len(high_divergence)} 篇")
    if high_divergence:
        for p in high_divergence:
            print(f"   - {p['paper']} ({p['round2_mean']:.2f}, std {p['round2_avg_std']:.2f})")

    # 对比分析
    all_scores = [p["round2_mean"] for p in papers]
    all_stds = [p["round2_avg_std"] for p in papers]

    print(f"\n对比分析:")
    print(f"  全部论文平均分: {sum(all_scores) / len(all_scores):.2f}")
    print(f"  全部论文平均标准差: {sum(all_stds) / len(all_stds):.2f}")
    print(f"  80+ 论文平均分: {sum(scores) / len(scores):.2f}")
    print(f"  80+ 论文平均标准差: {sum(stds) / len(stds):.2f}")
    print(f"  标准差差值: {sum(stds) / len(stds) - sum(all_stds) / len(all_stds):.2f}")

if __name__ == "__main__":
    main()
