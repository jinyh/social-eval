#!/usr/bin/env python3
"""从清洗后的论文列表中随机选择 10 篇用于测试"""

import json
import random
import argparse
from pathlib import Path
from collections import defaultdict


def select_papers(input_file: Path, output_file: Path, seed: int = 20260522):
    """
    从清洗后的论文列表中随机选择 10 篇

    期刊分布：
    - 中国法学：5 篇
    - 法学研究：3 篇
    - 中国社会科学：2 篇
    """
    # 设置随机种子
    random.seed(seed)

    # 读取清洗后的论文列表
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    papers = data["papers"]

    # 按期刊分组
    papers_by_journal = defaultdict(list)
    for paper in papers:
        journal = paper["journal"]
        papers_by_journal[journal].append(paper)

    # 检查每个期刊的论文数
    print("期刊论文数统计：")
    for journal, journal_papers in papers_by_journal.items():
        print(f"  {journal}: {len(journal_papers)} 篇")

    # 按目标分布随机选择
    target_distribution = {
        "中国法学": 5,
        "法学研究": 3,
        "中国社会科学": 2
    }

    selected_papers = []
    for journal, count in target_distribution.items():
        if journal not in papers_by_journal:
            print(f"警告：期刊 '{journal}' 不存在")
            continue

        available = papers_by_journal[journal]
        if len(available) < count:
            print(f"警告：期刊 '{journal}' 只有 {len(available)} 篇，少于目标 {count} 篇")
            count = len(available)

        selected = random.sample(available, count)
        selected_papers.extend(selected)

    # 重新分配 ID（1-10）
    for i, paper in enumerate(selected_papers, 1):
        paper["id"] = i

    # 输出结果
    output_data = {
        "total": len(selected_papers),
        "seed": seed,
        "distribution": {
            journal: sum(1 for p in selected_papers if p["journal"] == journal)
            for journal in target_distribution.keys()
        },
        "papers": selected_papers
    }

    # 保存到文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # 打印选择结果
    print(f"\n成功选择 {len(selected_papers)} 篇论文：")
    print(f"  随机种子：{seed}")
    print(f"  期刊分布：")
    for journal, count in output_data["distribution"].items():
        print(f"    {journal}: {count} 篇")
    print(f"\n输出文件：{output_file}")

    # 打印论文列表
    print("\n选中的论文：")
    for paper in selected_papers:
        filename = Path(paper["path"]).stem
        print(f"  {paper['id']:2d}. [{paper['journal']}] {filename[:60]}")


def main():
    parser = argparse.ArgumentParser(description="从清洗后的论文列表中随机选择 10 篇用于测试")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/phase2-paper-list-cleaned.json"),
        help="输入文件路径（清洗后的论文列表）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase2-test-10-papers.json"),
        help="输出文件路径"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260522,
        help="随机种子（用于可重复性）"
    )

    args = parser.parse_args()

    select_papers(args.input, args.output, args.seed)


if __name__ == "__main__":
    main()
