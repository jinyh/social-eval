#!/usr/bin/env python3
"""清洗论文列表，过滤非学术内容

用法：
    # Phase 2（默认）
    python scripts/clean_paper_list.py

    # Phase 3（补充论文）
    python scripts/clean_paper_list.py \\
        --input results/phase3-paper-list.json \\
        --output results/phase3-paper-list-cleaned.json \\
        --report results/phase3-paper-list-cleaning-report.md
"""

import argparse
import json
import re
from pathlib import Path

# 非学术内容关键词
NON_ACADEMIC_KEYWORDS = [
    "编委会",
    "巡视组",
    "工作动员会",
    "研讨会",
    "启事",
    "百强报刊",
    "致信祝贺",
    "主席声明",
    "笔谈",
    "会议纪要",
    "通知",
    "公告",
    "征稿",
]

def is_non_academic(title: str) -> bool:
    """判断是否为非学术内容"""
    for keyword in NON_ACADEMIC_KEYWORDS:
        if keyword in title:
            return True
    return False

def clean_paper_list(input_path: Path, output_path: Path, report_path: Path):
    """清洗论文列表，过滤非学术内容"""
    # 读取原始列表
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    original_papers = data["papers"]
    original_total = len(original_papers)

    # 过滤非学术内容
    cleaned_papers = []
    removed_papers = []

    for paper in original_papers:
        filename = Path(paper["path"]).stem
        if is_non_academic(filename):
            removed_papers.append(paper)
        else:
            cleaned_papers.append(paper)

    # 重新分配 ID
    for i, paper in enumerate(cleaned_papers, 1):
        paper["id"] = i

    # 统计期刊分布
    journal_counts = {}
    for paper in cleaned_papers:
        journal = paper["journal"]
        journal_counts[journal] = journal_counts.get(journal, 0) + 1

    # 保存清洗后的列表
    cleaned_data = {
        "total": len(cleaned_papers),
        "journals": journal_counts,
        "papers": cleaned_papers
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

    # 生成清洗报告
    report_lines = [
        "# 论文列表清洗报告",
        "",
        f"**清洗时间**：{Path(__file__).stat().st_mtime}",
        "",
        "## 清洗统计",
        "",
        f"- 原始论文数：{original_total} 篇",
        f"- 清洗后论文数：{len(cleaned_papers)} 篇",
        f"- 移除论文数：{len(removed_papers)} 篇",
        f"- 移除比例：{len(removed_papers)/original_total*100:.2f}%" if original_total > 0 else "- 移除比例：0%",
        "",
        "## 期刊分布（清洗后）",
        "",
    ]

    for journal, count in sorted(journal_counts.items()):
        report_lines.append(f"- {journal}：{count} 篇")

    report_lines.extend([
        "",
        "## 被移除的论文",
        "",
        "| 序号 | 期刊 | 论文标题 |",
        "|------|------|----------|",
    ])

    for i, paper in enumerate(removed_papers, 1):
        journal = paper["journal"]
        title = Path(paper["path"]).stem
        report_lines.append(f"| {i} | {journal} | {title} |")

    report_lines.extend([
        "",
        "## 移除原因",
        "",
        "以下关键词被识别为非学术内容：",
        "",
    ])

    for keyword in NON_ACADEMIC_KEYWORDS:
        report_lines.append(f"- {keyword}")

    report_lines.extend([
        "",
        "## 输出文件",
        "",
        f"- 清洗后列表：`{output_path}`",
        f"- 原始列表：`{input_path}`（已保留）",
        "",
    ])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding='utf-8')

    print(f"清洗完成！")
    print(f"  原始论文数：{original_total} 篇")
    print(f"  清洗后论文数：{len(cleaned_papers)} 篇")
    print(f"  移除论文数：{len(removed_papers)} 篇")
    print(f"  清洗报告：{report_path}")
    print(f"  清洗后列表：{output_path}")


def main():
    parser = argparse.ArgumentParser(description="清洗论文列表，过滤非学术内容")
    parser.add_argument(
        "--input",
        default="results/phase2-paper-list.json",
        help="输入文件路径（默认 results/phase2-paper-list.json）",
    )
    parser.add_argument(
        "--output",
        default="results/phase2-paper-list-cleaned.json",
        help="输出文件路径（默认 results/phase2-paper-list-cleaned.json）",
    )
    parser.add_argument(
        "--report",
        default="results/paper-list-cleaning-report.md",
        help="报告文件路径（默认 results/paper-list-cleaning-report.md）",
    )

    args = parser.parse_args()

    clean_paper_list(Path(args.input), Path(args.output), Path(args.report))


if __name__ == "__main__":
    main()
