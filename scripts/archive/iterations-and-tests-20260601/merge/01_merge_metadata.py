#!/usr/bin/env python3
"""
任务 1：合并元数据 CSV

读取 4 个 Excel 文件，合并为一个 CSV。
temp.xlsx 缺失的字段通过 ncpssd.org API 爬取补充。
"""

import csv
import json
import sys
import time
from pathlib import Path

import requests

# 确保可以导入 common 模块
sys.path.insert(0, str(Path(__file__).parent))
from common import (
    CSV_COLUMNS,
    load_excel_metadata,
    load_temp_xlsx,
)

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

EXCEL_FILES = [
    PROJECT_ROOT / "法学三大刊论文" / "11_法学研究_论文信息.xlsx",
    PROJECT_ROOT / "法学三大刊论文" / "4_中国法学_论文信息.xlsx",
    PROJECT_ROOT / "法学三大刊论文" / "8_中国社会科学_论文信息.xlsx",
]
TEMP_XLSX = PROJECT_ROOT / "法学三大刊论文" / "补充论文" / "temp.xlsx"

OUTPUT_CSV = PROJECT_ROOT / "results" / "merged-metadata.csv"
CACHE_DIR = PROJECT_ROOT / "results" / "merge_cache"
CACHE_FILE = CACHE_DIR / "ncpssd_metadata.json"

# ── API 配置 ──────────────────────────────────────────────
NCPSSD_API_URL = "https://www.ncpssd.org/articleinfoHandler/getjournalarticletable"
REQUEST_DELAY = 1.5  # 请求间隔（秒）
MAX_RETRIES = 3


def fetch_ncpssd_metadata(lngid: str) -> dict:
    """
    通过 ncpssd.org API 获取论文元数据。
    返回包含 showwriter, showorgan, pagecount, keywordc 的字典。
    """
    payload = {"lngid": lngid, "type": "1", "pageType": 1}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Content-Type": "application/json; charset=utf-8",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                NCPSSD_API_URL, json=payload, headers=headers, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("data"):
                d = data["data"]
                return {
                    "作者": d.get("showwriter", ""),
                    "作者机构": d.get("showorgan", ""),
                    "页数": d.get("pagecount", ""),
                    "主题词": d.get("keywordc", ""),
                }
            else:
                print(f"  ⚠️  API 返回空数据: {lngid}")
                return {}

        except Exception as e:
            wait = REQUEST_DELAY * (2 ** attempt)
            print(f"  ⚠️  请求失败 ({attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    return {}


def load_cached_metadata() -> dict:
    """加载已缓存的爬取结果"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cached_metadata(cache: dict):
    """保存爬取缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 60)
    print("任务 1：合并元数据 CSV")
    print("=" * 60)

    all_rows = []

    # 1. 读取三个主 Excel
    for excel_path in EXCEL_FILES:
        print(f"\n📖 读取 {excel_path.name}...")
        rows = load_excel_metadata(excel_path)
        print(f"   读取 {len(rows)} 行")
        all_rows.extend(rows)

    print(f"\n   三大刊合计: {len(all_rows)} 行")

    # 2. 读取 temp.xlsx
    print(f"\n📖 读取 {TEMP_XLSX.name}...")
    temp_rows = load_temp_xlsx(TEMP_XLSX)
    print(f"   读取 {len(temp_rows)} 行（已排除 FXYJ2025006013 目录页）")

    # 3. 补充 temp.xlsx 缺失字段
    cache = load_cached_metadata()
    missing_count = 0

    for row in temp_rows:
        lngid = row.get("_lngid", "")
        if not lngid:
            continue

        # 检查缓存
        if lngid in cache:
            cached = cache[lngid]
            row["作者"] = cached.get("作者", "")
            row["作者机构"] = cached.get("作者机构", "")
            row["页数"] = cached.get("页数", "")
            row["主题词"] = cached.get("主题词", "")
            continue

        # 需要爬取
        missing_count += 1

    if missing_count > 0:
        print(f"\n🌐 需要从 ncpssd.org 补充 {missing_count} 篇论文的元数据...")
        for row in temp_rows:
            lngid = row.get("_lngid", "")
            if not lngid or lngid in cache:
                continue

            print(f"   获取 {lngid} ({row.get('题目', '')[:30]}...)")
            metadata = fetch_ncpssd_metadata(lngid)

            if metadata:
                cache[lngid] = metadata
                row["作者"] = metadata.get("作者", "")
                row["作者机构"] = metadata.get("作者机构", "")
                row["页数"] = metadata.get("页数", "")
                row["主题词"] = metadata.get("主题词", "")
            else:
                print(f"   ❌ 获取失败: {lngid}")

            # 保存缓存（每次成功后保存，防止中断丢失）
            save_cached_metadata(cache)
            time.sleep(REQUEST_DELAY)

        print(f"   爬取完成，缓存已保存到 {CACHE_FILE}")
    else:
        print(f"\n✅ 所有 temp.xlsx 数据已缓存，无需重新爬取")

    # 将 temp 数据加入总列表（移除内部字段）
    for row in temp_rows:
        row.pop("_lngid", None)
        row.pop("_url", None)
    all_rows.extend(temp_rows)

    # 4. 写入 CSV
    print(f"\n📝 写入 CSV: {OUTPUT_CSV}")
    print(f"   总行数: {len(all_rows)}")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"   ✅ 写入完成")

    # 5. 验证
    print(f"\n📊 验证统计:")
    from collections import Counter

    journal_counts = Counter(row.get("期刊", "") for row in all_rows)
    for journal, count in sorted(journal_counts.items()):
        print(f"   {journal}: {count} 篇")
    print(f"   合计: {sum(journal_counts.values())} 篇")

    # 检查 temp.xlsx 来源的数据是否填充完整
    temp_filled = sum(
        1
        for row in temp_rows
        if row.get("作者") and row.get("作者机构") and row.get("页数")
    )
    print(f"   补充论文元数据完整度: {temp_filled}/{len(temp_rows)}")


if __name__ == "__main__":
    main()
