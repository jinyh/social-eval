#!/usr/bin/env python3
"""提取第二轮交叉评审平均分最高的 20 篇论文"""

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

    # 按平均分降序排序
    papers.sort(key=lambda x: x["round2_mean"], reverse=True)

    # 输出前 20 篇
    print("=" * 100)
    print("第二轮交叉评审平均分最高的 20 篇论文")
    print("=" * 100)
    print(f"{'排名':<6} {'平均分':<10} {'平均标准差':<12} {'论文标题'}")
    print("-" * 100)

    for i, paper in enumerate(papers[:20], 1):
        print(f"{i:<6} {paper['round2_mean']:<10.2f} {paper['round2_avg_std']:<12.2f} {paper['paper']}")

    print("=" * 100)
    print(f"\n总计 {len(papers)} 篇论文参与第二轮评审")

if __name__ == "__main__":
    main()
