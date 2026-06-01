#!/usr/bin/env python3
"""
任务 2：合并 paper-list + 重命名 PDF

合并 phase2 和 phase3 的 paper-list-cleaned.json，
将被评测的论文 PDF 复制到 raw/fullpaper/ 并重命名。
"""

import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    fuzzy_match_title,
    load_excel_metadata,
    load_temp_xlsx,
    sanitize_filename,
)

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PHASE2_JSON = PROJECT_ROOT / "results" / "phase2-paper-list-cleaned.json"
PHASE3_JSON = PROJECT_ROOT / "results" / "phase3-paper-list-cleaned.json"

EXCEL_FILES = [
    PROJECT_ROOT / "法学三大刊论文" / "11_法学研究_论文信息.xlsx",
    PROJECT_ROOT / "法学三大刊论文" / "4_中国法学_论文信息.xlsx",
    PROJECT_ROOT / "法学三大刊论文" / "8_中国社会科学_论文信息.xlsx",
]
TEMP_XLSX = PROJECT_ROOT / "法学三大刊论文" / "补充论文" / "temp.xlsx"
CACHE_DIR = PROJECT_ROOT / "results" / "merge_cache"
NCPSSD_CACHE = CACHE_DIR / "ncpssd_metadata.json"

OUTPUT_JSON = PROJECT_ROOT / "results" / "paper-list.json"
FULLPAPER_DIR = PROJECT_ROOT / "raw" / "fullpaper"
UNMATCHED_CSV = CACHE_DIR / "unmatched_papers.csv"
MAPPING_CACHE = CACHE_DIR / "pdf_mapping.json"

# Phase 3 起始 ID
PHASE3_START_ID = 1837


def build_excel_index() -> dict[str, list[dict]]:
    """
    构建 Excel 元数据索引：{期刊名: [{题目, 作者, 作者机构, ...}]}
    """
    index = {}
    for excel_path in EXCEL_FILES:
        rows = load_excel_metadata(excel_path)
        for row in rows:
            journal = row.get("期刊", "")
            if journal not in index:
                index[journal] = []
            index[journal].append(row)
    return index


def build_temp_index() -> dict[str, dict]:
    """
    构建 temp.xlsx 元数据索引：{lngid: {作者, 作者机构, ...}}
    优先使用爬取缓存中的数据。
    """
    # 加载爬取缓存
    cache = {}
    if NCPSSD_CACHE.exists():
        with open(NCPSSD_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)

    temp_rows = load_temp_xlsx(TEMP_XLSX)
    index = {}

    for row in temp_rows:
        lngid = row.get("_lngid", "")
        if not lngid:
            continue

        # 用缓存数据补充
        if lngid in cache:
            row["作者"] = cache[lngid].get("作者", "")
            row["作者机构"] = cache[lngid].get("作者机构", "")
            row["页数"] = cache[lngid].get("页数", "")
            row["主题词"] = cache[lngid].get("主题词", "")

        index[lngid] = row

    return index


def match_pdf_to_metadata(
    pdf_stem: str, journal: str, excel_index: dict[str, list[dict]]
) -> dict | None:
    """
    将 PDF 文件名匹配到 Excel 元数据。
    返回匹配到的元数据字典，未匹配返回 None。
    """
    candidates = excel_index.get(journal, [])
    if not candidates:
        return None

    best_match = None
    best_score = 0.0

    for row in candidates:
        titlec = row.get("题目", "")
        if not titlec:
            continue
        score = fuzzy_match_title(pdf_stem, titlec)
        if score > best_score:
            best_score = score
            best_match = row

    # 最低阈值
    if best_score >= 0.85:
        return best_match
    return None


def extract_first_author(showwriter: str) -> str:
    """从 showwriter 字段提取第一作者名（去掉序号标记）"""
    if not showwriter:
        return ""
    # 格式通常是 "张三[1];李四[2]" 或 "张三[1,2]"
    first = showwriter.split(";")[0].strip()
    # 去掉 [1] 等标记
    import re

    first = re.sub(r"\[.*?\]", "", first).strip()
    return first


def extract_first_org(showorgan: str) -> str:
    """从 showorgan 字段提取第一机构名（去掉序号标记）"""
    if not showorgan:
        return ""
    # 格式通常是 "[1]华东政法大学;[2]中国社科院"
    first = showorgan.split(";")[0].strip()
    import re

    first = re.sub(r"\[\d+\]", "", first).strip()
    return first


def make_new_filename(
    paper_id: int,
    journal: str,
    year,
    num,
    title: str,
    author: str,
    org: str,
) -> str:
    """生成新 PDF 文件名"""
    # 编码 4 位补零
    id_str = f"{paper_id:04d}"
    year_str = str(year) if year else ""
    num_str = str(num) if num else ""

    # 清理各字段
    parts = [id_str, journal, year_str, num_str, title, author, org]
    cleaned = [sanitize_filename(p) for p in parts]

    filename = "-".join(cleaned) + ".pdf"
    return filename


def main():
    print("=" * 60)
    print("任务 2：合并 paper-list + 重命名 PDF")
    print("=" * 60)

    # 1. 加载 phase2 和 phase3 paper list
    print("\n📖 加载 paper list...")
    with open(PHASE2_JSON, "r", encoding="utf-8") as f:
        phase2_data = json.load(f)
    with open(PHASE3_JSON, "r", encoding="utf-8") as f:
        phase3_data = json.load(f)

    phase2_papers = phase2_data["papers"]
    phase3_papers = phase3_data["papers"]
    print(f"   Phase 2: {len(phase2_papers)} 篇")
    print(f"   Phase 3: {len(phase3_papers)} 篇")

    # 2. 构建 Excel 索引
    print("\n📖 构建 Excel 元数据索引...")
    excel_index = build_excel_index()
    for journal, rows in excel_index.items():
        print(f"   {journal}: {len(rows)} 条")

    temp_index = build_temp_index()
    print(f"   补充论文: {len(temp_index)} 条")

    # 3. 创建输出目录
    FULLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 4. 处理论文并生成新文件
    print("\n📦 处理论文...")
    merged_papers = []
    journal_counts = Counter()
    unmatched = []
    mapping = {}
    copy_errors = []

    # 4a. 处理 Phase 2 论文
    print("\n   Phase 2:")
    for i, paper in enumerate(phase2_papers):
        paper_id = paper["id"]
        old_path = PROJECT_ROOT / paper["path"]
        journal = paper["journal"]
        pdf_stem = Path(paper["filename"]).stem

        # 匹配元数据
        metadata = match_pdf_to_metadata(pdf_stem, journal, excel_index)

        if metadata:
            author = extract_first_author(metadata.get("作者", ""))
            org = extract_first_org(metadata.get("作者机构", ""))
            year = metadata.get("年份", "")
            num = metadata.get("期", "")
            title = metadata.get("题目", pdf_stem)
        else:
            unmatched.append(
                {
                    "id": paper_id,
                    "journal": journal,
                    "filename": paper["filename"],
                    "reason": "无法匹配 Excel 元数据",
                }
            )
            # 使用已有信息作为 fallback
            author = ""
            org = ""
            year = ""
            num = ""
            title = pdf_stem

        # 生成新文件名
        new_filename = make_new_filename(
            paper_id, journal, year, num, title, author, org
        )
        new_path = FULLPAPER_DIR / new_filename

        # 复制文件
        if old_path.exists():
            shutil.copy2(old_path, new_path)
        else:
            copy_errors.append(
                {"id": paper_id, "old_path": str(old_path), "error": "源文件不存在"}
            )

        # 记录映射
        new_paper = {
            "id": paper_id,
            "path": f"raw/fullpaper/{new_filename}",
            "journal": journal,
            "filename": new_filename,
            "source": "phase2",
        }
        merged_papers.append(new_paper)
        mapping[str(paper_id)] = {
            "old_path": paper["path"],
            "new_path": new_paper["path"],
            "old_filename": paper["filename"],
            "new_filename": new_filename,
        }
        journal_counts[journal] += 1

        if (i + 1) % 200 == 0:
            print(f"   已处理 {i + 1}/{len(phase2_papers)}...")

    print(f"   Phase 2 完成: {len(phase2_papers)} 篇")

    # 4b. 处理 Phase 3 论文
    print("\n   Phase 3:")
    for i, paper in enumerate(phase3_papers):
        new_id = PHASE3_START_ID + i
        old_path = PROJECT_ROOT / paper["path"]
        journal = paper["journal"]
        old_filename = paper["filename"]

        # Phase 3 的 PDF 文件名格式: {lngid}_{mediac}_{years}_{titlec}.pdf
        parts = old_filename.rsplit(".", 1)[0].split("_", 3)
        lngid = parts[0] if len(parts) > 0 else ""
        # mediac = parts[1] if len(parts) > 1 else journal
        # years = parts[2] if len(parts) > 2 else ""
        titlec = parts[3] if len(parts) > 3 else old_filename

        # 从 temp_index 获取作者/机构
        temp_meta = temp_index.get(lngid, {})
        author = extract_first_author(temp_meta.get("作者", ""))
        org = extract_first_org(temp_meta.get("作者机构", ""))
        year = temp_meta.get("年份", "")
        num = temp_meta.get("期", "")
        title = temp_meta.get("题目", titlec)

        if not author:
            unmatched.append(
                {
                    "id": new_id,
                    "journal": journal,
                    "filename": old_filename,
                    "reason": "temp.xlsx 缺少作者数据",
                }
            )

        # 生成新文件名
        new_filename = make_new_filename(
            new_id, journal, year, num, title, author, org
        )
        new_path = FULLPAPER_DIR / new_filename

        # 复制文件
        if old_path.exists():
            shutil.copy2(old_path, new_path)
        else:
            copy_errors.append(
                {"id": new_id, "old_path": str(old_path), "error": "源文件不存在"}
            )

        # 记录映射
        new_paper = {
            "id": new_id,
            "path": f"raw/fullpaper/{new_filename}",
            "journal": journal,
            "filename": new_filename,
            "source": "phase3",
        }
        merged_papers.append(new_paper)
        mapping[str(new_id)] = {
            "old_path": paper["path"],
            "new_path": new_paper["path"],
            "old_filename": old_filename,
            "new_filename": new_filename,
        }
        journal_counts[journal] += 1

    print(f"   Phase 3 完成: {len(phase3_papers)} 篇")

    # 5. 写入合并后的 paper-list.json
    print(f"\n📝 写入 paper-list.json...")
    merged_data = {
        "total": len(merged_papers),
        "journals": dict(journal_counts),
        "papers": merged_papers,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    print(f"   ✅ {OUTPUT_JSON}")

    # 6. 写入映射缓存
    with open(MAPPING_CACHE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    # 7. 写入未匹配列表
    if unmatched:
        with open(UNMATCHED_CSV, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "journal", "filename", "reason"]
            )
            writer.writeheader()
            writer.writerows(unmatched)
        print(f"   ⚠️  {len(unmatched)} 篇未匹配，已保存到 {UNMATCHED_CSV}")

    # 8. 报告复制错误
    if copy_errors:
        print(f"   ❌ {len(copy_errors)} 个文件复制失败:")
        for err in copy_errors[:5]:
            print(f"      ID {err['id']}: {err['error']} - {err['old_path']}")

    # 9. 验证
    print(f"\n📊 验证统计:")
    print(f"   paper-list.json 论文数: {len(merged_papers)}")
    print(f"   raw/fullpaper/ 文件数: {len(list(FULLPAPER_DIR.glob('*.pdf')))}")
    print(f"   期刊分布:")
    for journal, count in sorted(journal_counts.items()):
        print(f"     {journal}: {count}")
    print(f"   Phase 3 起始 ID: {PHASE3_START_ID}")
    print(f"   Phase 3 结束 ID: {PHASE3_START_ID + len(phase3_papers) - 1}")
    print(f"   未匹配数: {len(unmatched)}")
    print(f"   复制失败数: {len(copy_errors)}")


if __name__ == "__main__":
    main()
