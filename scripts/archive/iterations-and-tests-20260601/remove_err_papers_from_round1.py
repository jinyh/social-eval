#!/usr/bin/env python3
"""从 round1 中删除 round1-err 2-5 类的论文"""

import json
from pathlib import Path
import shutil

def main():
    base_dir = Path("results/phase2-evaluation")
    round1_dir = base_dir / "round1"
    round1_err_dir = base_dir / "round1-err"

    # 要删除的分类
    categories = [
        "2-all-reject",
        "3-majority-reject",
        "4-single-reject",
        "5-boundary-only"
    ]

    deleted_papers = []
    not_found_papers = []

    print("开始从 round1 中删除 round1-err 2-5 类的论文...\n")

    for category in categories:
        cat_dir = round1_err_dir / category
        if not cat_dir.exists():
            print(f"⚠️  目录不存在: {category}")
            continue

        json_files = sorted(cat_dir.glob("paper-*.json"))
        print(f"📁 {category}: 找到 {len(json_files)} 篇论文")

        for paper_path in json_files:
            paper_name = paper_path.name
            round1_paper_path = round1_dir / paper_name

            if round1_paper_path.exists():
                # 删除文件
                round1_paper_path.unlink()
                deleted_papers.append({
                    "category": category,
                    "paper": paper_name
                })
                print(f"  ✅ 已删除: {paper_name}")
            else:
                not_found_papers.append({
                    "category": category,
                    "paper": paper_name
                })
                print(f"  ⚠️  未找到: {paper_name}")

    # 保存删除记录
    deletion_log = {
        "deleted_count": len(deleted_papers),
        "not_found_count": len(not_found_papers),
        "deleted_papers": deleted_papers,
        "not_found_papers": not_found_papers
    }

    log_path = base_dir / "round1-deletion-log.json"
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(deletion_log, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print("删除完成")
    print(f"{'='*60}")
    print(f"✅ 成功删除: {len(deleted_papers)} 篇")
    print(f"⚠️  未找到: {len(not_found_papers)} 篇")
    print(f"\n删除记录已保存到: {log_path}")

    # 统计 round1 剩余论文数
    remaining_count = len(list(round1_dir.glob("paper-*.json")))
    print(f"\nround1 剩余论文数: {remaining_count}")

if __name__ == "__main__":
    main()
