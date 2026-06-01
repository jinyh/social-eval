#!/usr/bin/env python3
"""生成论文列表

扫描期刊目录，生成完整论文路径列表。支持两种模式：
- 默认模式：扫描三大刊主目录（中国法学、中国社会科学、法学研究）
- 自定义模式：通过 --input-dir 指定任意目录（如补充论文）

用法：
    # Phase 2（默认）
    python scripts/generate_paper_list.py

    # Phase 3（补充论文）
    python scripts/generate_paper_list.py \\
        --input-dir "法学三大刊论文/补充论文" \\
        --output results/phase3-paper-list.json
"""

import argparse
import json
from pathlib import Path


def parse_journal_from_filename(filename: str) -> str:
    """从补充论文文件名解析期刊名

    补充论文命名格式：[代码][年份][期号][序号]_[期刊名]_[年份]_[标题].pdf
    期刊名在第二个 _ 分隔段。
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) >= 2:
        journal = parts[1]
        if journal in ("法学研究", "中国法学", "中国社会科学"):
            return journal
    # fallback: 前缀推断
    code = parts[0] if parts else stem
    prefix_map = {"FXYJ": "法学研究", "ZGFX": "中国法学", "ZGSHKX": "中国社会科学"}
    for prefix, name in prefix_map.items():
        if code.startswith(prefix):
            return name
    return "未知期刊"


def generate_from_main_dirs(output_path: Path):
    """默认模式：扫描三大刊主目录"""
    journal_dirs = [
        ("法学三大刊论文/中国法学", "中国法学"),
        ("法学三大刊论文/中国社会科学", "中国社会科学"),
        ("法学三大刊论文/法学研究", "法学研究")
    ]

    papers = []
    paper_id = 1

    for dir_path, journal_name in journal_dirs:
        dir_full_path = Path(dir_path)

        if not dir_full_path.exists():
            print(f"警告: 目录不存在 {dir_path}")
            continue

        pdf_files = sorted(dir_full_path.glob("*.pdf"))
        print(f"扫描 {journal_name}: {len(pdf_files)} 篇论文")

        for pdf_file in pdf_files:
            papers.append({
                "id": paper_id,
                "path": str(pdf_file),
                "journal": journal_name,
                "filename": pdf_file.name
            })
            paper_id += 1

    save_paper_list(papers, output_path)


def generate_from_custom_dir(input_dir: Path, output_path: Path):
    """自定义模式：扫描指定目录，从文件名解析期刊"""
    if not input_dir.exists():
        print(f"错误: 目录不存在 {input_dir}")
        return

    pdf_files = sorted(input_dir.glob("*.pdf"))
    print(f"扫描 {input_dir}: {len(pdf_files)} 篇论文")

    papers = []
    for paper_id, pdf_file in enumerate(pdf_files, 1):
        journal = parse_journal_from_filename(pdf_file.name)
        papers.append({
            "id": paper_id,
            "path": str(pdf_file),
            "journal": journal,
            "filename": pdf_file.name
        })

    save_paper_list(papers, output_path)


def save_paper_list(papers: list[dict], output_path: Path):
    """保存论文列表到 JSON"""
    # 统计期刊分布
    journal_counts = {}
    for paper in papers:
        journal = paper["journal"]
        journal_counts[journal] = journal_counts.get(journal, 0) + 1

    print(f"\n总计: {len(papers)} 篇论文")
    for journal, count in sorted(journal_counts.items()):
        print(f"  {journal}: {count} 篇")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "total": len(papers),
        "journals": journal_counts,
        "papers": papers
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n论文列表已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="生成论文列表")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="论文目录路径（默认扫描三大刊主目录）",
    )
    parser.add_argument(
        "--output",
        default="results/phase2-paper-list.json",
        help="输出文件路径（默认 results/phase2-paper-list.json）",
    )

    args = parser.parse_args()

    if args.input_dir:
        generate_from_custom_dir(Path(args.input_dir), Path(args.output))
    else:
        generate_from_main_dirs(Path(args.output))


if __name__ == "__main__":
    main()
