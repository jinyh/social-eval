#!/usr/bin/env python3
"""从 xlsx 提取被评论文元数据，输出 1 个 markdown 汇总 + 3 个按期刊分的 CSV

用法：
    uv run python scripts/generate_paper_metadata.py
"""

import csv
import io
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import openpyxl


# === 配置 ===

XLSX_FILES = {
    '中国法学': '法学三大刊论文/4_中国法学_论文信息.xlsx',
    '法学研究': '法学三大刊论文/11_法学研究_论文信息.xlsx',
    '中国社会科学': '法学三大刊论文/8_中国社会科学_论文信息.xlsx',
}

CLEANED_LIST = 'results/phase2-paper-list-cleaned.json'

OUTPUT_DIR = 'results'
SUMMARY_MD = f'{OUTPUT_DIR}/phase2-paper-metadata-summary.md'

CSV_COLUMNS = [
    'id', 'title', 'author', 'first_author_org', 'year', 'issue',
    'page_start', 'page_end', 'abstract', 'keywords', 'clc_code',
    'cite_count', 'doi', 'pdf_path',
]

# xlsx 列名到 CSV 列名的映射
XLSX_TO_CSV = {
    'titlec': 'title',
    'showwriter': 'author',
    'firstorgan': 'first_author_org',
    'years': 'year',
    'num': 'issue',
    'beginpage': 'page_start',
    'endpage': 'page_end',
    'remarkc': 'abstract',
    'keywordc': 'keywords',
    'clazz': 'clc_code',
    'refercount': 'cite_count',
    'doi': 'doi',
}


def normalize_title(s: str) -> str:
    """归一化标题用于匹配：去掉所有非中文非字母数字字符"""
    if not s:
        return ''
    # 去掉 PDF 文件名中的 (1)、(2) 等重复后缀
    s = re.sub(r'\s*\(\d+\)\s*$', '', s)
    # 去掉所有非中文非字母数字字符（包括 _、:、：、空格、标点等）
    return re.sub(r'[^一-鿿a-zA-Z0-9]', '', s).lower()


def load_cleaned_list() -> list[dict]:
    """加载清洗后的论文列表"""
    with open(PROJECT_ROOT / CLEANED_LIST, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['papers']


def load_xlsx_metadata(journal: str, xlsx_path: str) -> dict[str, dict]:
    """加载 xlsx 元数据，返回 {归一化标题: 字段字典}"""
    wb = openpyxl.load_workbook(PROJECT_ROOT / xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    wb.close()

    # 建立列名索引
    col_idx = {col: headers.index(col) for col in XLSX_TO_CSV.keys() if col in headers}

    result = {}
    for row in rows[1:]:
        title_raw = row[col_idx.get('titlec', 0)] if 'titlec' in col_idx else None
        if not title_raw:
            continue

        key = normalize_title(str(title_raw))
        if not key:
            continue

        record = {}
        for xlsx_col, csv_col in XLSX_TO_CSV.items():
            if xlsx_col in col_idx:
                val = row[col_idx[xlsx_col]]
                record[csv_col] = val if val is not None else ''
            else:
                record[csv_col] = ''

        # 清理 CLC 分类号：去方括号，取逗号分隔的第一个
        clc = str(record.get('clc_code', '')).strip()
        if clc:
            clc = clc.strip('[]')
            if ',' in clc:
                clc = clc.split(',')[0].strip()
            record['clc_code'] = clc

        # 清理机构：去掉 "0" 值
        org = str(record.get('first_author_org', '')).strip()
        if org in ('', '0', 'None'):
            record['first_author_org'] = ''

        result[key] = record

    return result


def match_papers(papers: list[dict], xlsx_data: dict[str, dict[str, dict]]) -> tuple[list[dict], list[dict]]:
    """匹配论文列表和 xlsx 元数据

    Returns:
        (matched_records, unmatched_papers)
    """
    matched = []
    unmatched = []

    for paper in papers:
        journal = paper['journal']
        filename = paper['filename']
        title_from_pdf = filename.replace('.pdf', '')

        # 去掉 (1) 后缀
        title_from_pdf = re.sub(r'\s*\(\d+\)\s*$', '', title_from_pdf)

        key = normalize_title(title_from_pdf)

        xlsx_for_journal = xlsx_data.get(journal, {})
        record = xlsx_for_journal.get(key)

        if record:
            row = {'id': paper['id'], 'pdf_path': paper['path']}
            row.update(record)
            matched.append((journal, row))
        else:
            unmatched.append(paper)

    return matched, unmatched


def write_csv_by_journal(matched: list[tuple[str, dict]]):
    """按期刊写入 CSV 文件"""
    # 按期刊分组
    by_journal = {}
    for journal, row in matched:
        by_journal.setdefault(journal, []).append(row)

    for journal, rows in by_journal.items():
        output_path = PROJECT_ROOT / OUTPUT_DIR / f'phase2-metadata-{journal}.csv'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # UTF-8 BOM 编码
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
            writer.writeheader()
            for row in sorted(rows, key=lambda r: r['id']):
                # 清理 None 值
                cleaned_row = {k: (v if v is not None else '') for k, v in row.items()}
                writer.writerow(cleaned_row)

        print(f'  {journal}: {len(rows)} 篇 → {output_path.name}')


def generate_summary_md(matched: list[tuple[str, dict]], unmatched: list[dict]):
    """生成 markdown 汇总"""
    # 按期刊分组统计
    by_journal = {}
    for journal, row in matched:
        by_journal.setdefault(journal, []).append(row)

    total = len(matched)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines = []
    lines.append(f'# Phase 2 被评论文元数据汇总')
    lines.append('')
    lines.append(f'> 生成时间：{now}')
    lines.append(f'> 数据源：法学三大刊论文信息 xlsx + phase2-paper-list-cleaned.json')
    lines.append(f'> 匹配论文：{total} 篇 | 未匹配：{len(unmatched)} 篇')
    lines.append('')

    # 期刊分布
    lines.append('## 期刊分布')
    lines.append('')
    lines.append('| 期刊 | 篇数 | 年份范围 | 平均被引 |')
    lines.append('|------|------|---------|---------|')

    for journal in ['中国法学', '法学研究', '中国社会科学']:
        rows = by_journal.get(journal, [])
        years = [int(r['year']) for r in rows if r.get('year') and str(r['year']).isdigit()]
        cite_counts = [int(r['cite_count']) for r in rows if r.get('cite_count') and str(r['cite_count']).isdigit()]
        year_range = f'{min(years)}-{max(years)}' if years else '未知'
        avg_cite = f'{statistics.mean(cite_counts):.1f}' if cite_counts else '未知'
        lines.append(f'| {journal} | {len(rows)} | {year_range} | {avg_cite} |')

    lines.append('')

    # 最高被引论文 Top 15
    lines.append('## 最高被引论文 Top 15')
    lines.append('')
    lines.append('| 排名 | 标题 | 期刊 | 年份 | 被引 |')
    lines.append('|------|------|------|------|------|')

    all_rows = [(journal, row) for journal, row in matched]
    rows_with_cite = [
        (j, r) for j, r in all_rows
        if r.get('cite_count') and str(r['cite_count']).isdigit()
    ]
    rows_with_cite.sort(key=lambda x: int(x[1]['cite_count']), reverse=True)

    for rank, (journal, row) in enumerate(rows_with_cite[:15], 1):
        title = str(row.get('title', ''))[:40]
        lines.append(f'| {rank} | {title} | {journal} | {row.get("year", "")} | {row.get("cite_count", "")} |')

    lines.append('')

    # CLC 分类号分布 Top 20
    lines.append('## CLC 分类号分布 Top 20')
    lines.append('')
    lines.append('| 分类号 | 篇数 | 占比 |')
    lines.append('|--------|------|------|')

    clc_counter = Counter()
    for _, row in matched:
        clc = row.get('clc_code', '')
        if clc:
            # 取前4位作为大类（如 D924 -> D924）
            clc_counter[str(clc).strip()] += 1

    for clc, count in clc_counter.most_common(20):
        pct = f'{count/total*100:.1f}%'
        lines.append(f'| {clc} | {count} | {pct} |')

    lines.append('')

    # 第一作者机构 Top 20
    lines.append('## 第一作者机构 Top 20')
    lines.append('')
    lines.append('| 机构 | 篇数 | 占比 |')
    lines.append('|------|------|------|')

    org_counter = Counter()
    for _, row in matched:
        org = row.get('first_author_org', '')
        if org:
            # 清理机构名（去掉 [1] 等标注）
            org = re.sub(r'\[\d+\]', '', str(org)).strip()
            if org:
                org_counter[org] += 1

    for org, count in org_counter.most_common(20):
        pct = f'{count/total*100:.1f}%'
        lines.append(f'| {org} | {count} | {pct} |')

    lines.append('')

    # 年份分布
    lines.append('## 发表年份分布')
    lines.append('')
    lines.append('| 年份 | 篇数 |')
    lines.append('|------|------|')

    year_counter = Counter()
    for _, row in matched:
        year = row.get('year', '')
        if year and str(year).isdigit():
            year_counter[int(year)] += 1

    for year in sorted(year_counter.keys()):
        lines.append(f'| {year} | {year_counter[year]} |')

    lines.append('')

    # 字段填充率
    lines.append('## 元数据字段填充率')
    lines.append('')
    lines.append('| 字段 | 中国法学 | 法学研究 | 中国社会科学 | 说明 |')
    lines.append('|------|---------|---------|------------|------|')

    field_labels = {
        'title': '标题', 'author': '作者', 'first_author_org': '第一作者机构',
        'year': '发表年份', 'issue': '期号', 'page_start': '起始页',
        'abstract': '摘要', 'keywords': '关键词', 'clc_code': 'CLC分类号',
        'cite_count': '被引次数', 'doi': 'DOI',
    }
    field_notes = {
        'doi': 'xlsx 源数据全空',
        'cite_count': '近年论文无引用数据',
        'first_author_org': '部分论文未标注',
    }

    all_by_journal = {}
    for journal, row in matched:
        all_by_journal.setdefault(journal, []).append(row)

    for field, label in field_labels.items():
        rates = []
        for journal in ['中国法学', '法学研究', '中国社会科学']:
            rows = all_by_journal.get(journal, [])
            filled = sum(1 for r in rows if str(r.get(field, '')).strip())
            total_j = len(rows)
            pct = f'{filled/total_j*100:.0f}%' if total_j else '-'
            rates.append(pct)
        note = field_notes.get(field, '')
        lines.append(f'| {label} | {rates[0]} | {rates[1]} | {rates[2]} | {note} |')

    lines.append('')

    # 未匹配论文
    if unmatched:
        lines.append('## 未匹配到 xlsx 元数据的论文')
        lines.append('')
        lines.append(f'共 {len(unmatched)} 篇（将使用空元数据）：')
        lines.append('')
        lines.append('| 期刊 | 文件名 |')
        lines.append('|------|--------|')
        for p in unmatched:
            lines.append(f'| {p["journal"]} | {p["filename"]} |')

    output_path = PROJECT_ROOT / SUMMARY_MD
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'  汇总: {output_path.name}')


def main():
    print('读取清洗后论文列表...')
    papers = load_cleaned_list()
    print(f'  共 {len(papers)} 篇')

    print('读取 xlsx 元数据...')
    xlsx_data = {}
    for journal, xlsx_path in XLSX_FILES.items():
        xlsx_data[journal] = load_xlsx_metadata(journal, xlsx_path)
        print(f'  {journal}: {len(xlsx_data[journal])} 条记录')

    print('匹配论文...')
    matched, unmatched = match_papers(papers, xlsx_data)
    print(f'  匹配: {len(matched)}/{len(papers)}')
    print(f'  未匹配: {len(unmatched)}')

    if unmatched:
        print('\n  未匹配的论文:')
        for p in unmatched[:10]:
            print(f'    [{p["journal"]}] {p["filename"]}')
        if len(unmatched) > 10:
            print(f'    ... 等 {len(unmatched)} 篇')

    print('\n写入 CSV...')
    write_csv_by_journal(matched)

    print('生成 markdown 汇总...')
    generate_summary_md(matched, unmatched)

    print('\n完成！')


if __name__ == '__main__':
    main()
