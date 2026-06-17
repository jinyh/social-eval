#!/usr/bin/env python3
"""
生成"专家确认.csv"

数据源：
1. 新分类修改版-未标黄.csv（Excel 转换，已手动筛选）
2. paper-list.md（102 篇）
3. e2-paper-list.md（101 篇）

排除规则：
- 排除"专家纠正学科分类汇总.md"中的所有 33 个 PID

输出格式（参照"专家纠正学科分类汇总.md"）：
编号,期刊,年份,题目,作者,机构,专家分类
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Set


def parse_markdown_table(content: str) -> List[Dict[str, str]]:
    """解析 Markdown 表格"""
    lines = content.strip().split('\n')

    # 找到表头分隔行（包含多个 --- 的行）
    header_sep_idx = None
    for i, line in enumerate(lines):
        if '|' in line and '--' in line:
            # 检查是否是分隔符行（包含多个连字符）
            parts = line.split('|')
            if len([p for p in parts if '-' in p]) >= 2:
                header_sep_idx = i
                break

    if header_sep_idx is None or header_sep_idx == 0:
        return []

    # 解析表头
    header_line = lines[header_sep_idx - 1]
    headers = [h.strip() for h in header_line.split('|')]
    headers = [h for h in headers if h]  # 去掉空字符串

    # 解析数据行
    results = []
    for line in lines[header_sep_idx + 1:]:
        line = line.strip()
        if not line or not line.startswith('|'):
            continue

        # 跳过空行或其他非数据行
        if line.count('|') < 2:
            continue

        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c or c == '']  # 保留所有单元格（包括空的）

        # 去掉首尾可能的空元素
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]

        if len(cells) != len(headers):
            continue

        row = dict(zip(headers, cells))
        results.append(row)

    return results


def load_expert_corrections(filepath: Path) -> Set[int]:
    """读取专家纠正汇总，提取所有需要排除的 PID"""
    content = filepath.read_text(encoding='utf-8')
    rows = parse_markdown_table(content)

    exclude_pids = set()
    for row in rows:
        pid_str = row.get('编号', '').strip()
        if pid_str and pid_str.isdigit():
            exclude_pids.add(int(pid_str))

    print(f"✓ 从专家纠正汇总中提取 {len(exclude_pids)} 个需要排除的 PID")
    return exclude_pids


def load_paper_list_md(filepath: Path, exclude_pids: Set[int]) -> Dict[int, Dict[str, str]]:
    """读取 paper-list.md"""
    content = filepath.read_text(encoding='utf-8')
    rows = parse_markdown_table(content)

    papers = {}
    excluded_count = 0

    for row in rows:
        pid_str = row.get('PID', '').strip()
        if not pid_str or not pid_str.isdigit():
            continue

        pid = int(pid_str)

        # 排除
        if pid in exclude_pids:
            excluded_count += 1
            continue

        papers[pid] = {
            '编号': str(pid),
            '题目': row.get('题目', '').strip(),
            '作者': row.get('作者', '').strip(),
            '期刊': row.get('期刊', '').strip(),
            '年份': row.get('年份', '').strip(),
            '机构': row.get('机构', '').strip(),
            '专家分类': row.get('分类', '').strip(),
        }

    print(f"✓ paper-list.md: 读取 {len(rows)} 条，排除 {excluded_count} 条，保留 {len(papers)} 条")
    return papers


def load_e2_paper_list_md(filepath: Path, exclude_pids: Set[int]) -> Dict[int, Dict[str, str]]:
    """读取 e2-paper-list.md"""
    content = filepath.read_text(encoding='utf-8')
    rows = parse_markdown_table(content)

    papers = {}
    excluded_count = 0

    for row in rows:
        pid_str = row.get('PID', '').strip()
        if not pid_str or not pid_str.isdigit():
            continue

        pid = int(pid_str)

        # 排除
        if pid in exclude_pids:
            excluded_count += 1
            continue

        papers[pid] = {
            '编号': str(pid),
            '题目': row.get('题目', '').strip(),
            '作者': row.get('作者', '').strip(),
            '期刊': row.get('期刊', '').strip(),
            '年份': row.get('年份', '').strip(),
            '机构': row.get('机构', '').strip(),
            '专家分类': row.get('学科', '').strip(),
        }

    print(f"✓ e2-paper-list.md: 读取 {len(rows)} 条，排除 {excluded_count} 条，保留 {len(papers)} 条")
    return papers


def load_excel_csv(filepath: Path, exclude_pids: Set[int]) -> Dict[int, Dict[str, str]]:
    """读取 Excel 转换的 CSV（已由用户手动筛选未标黄）"""
    papers = {}
    excluded_count = 0

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        total_rows = 0

        for row in reader:
            total_rows += 1

            # 尝试多种可能的 PID 字段名
            pid_str = None
            for key in ['编号', 'PID', 'pid', '序号', '#']:
                if key in row:
                    pid_str = row[key].strip()
                    break

            if not pid_str or not pid_str.isdigit():
                continue

            pid = int(pid_str)

            # 排除
            if pid in exclude_pids:
                excluded_count += 1
                continue

            # 构建标准字段（尝试多种可能的字段名）
            papers[pid] = {
                '编号': str(pid),
                '题目': row.get('题目', row.get('标题', '')).strip(),
                '作者': row.get('作者', '').strip(),
                '期刊': row.get('期刊', row.get('来源', '')).strip(),
                '年份': row.get('年份', row.get('年', '')).strip(),
                '机构': row.get('机构', row.get('单位', row.get('作者机构', ''))).strip(),
                '专家分类': row.get('新分类(主)', row.get('专家分类', row.get('学科', row.get('分类', '')))).strip(),
            }

    print(f"✓ Excel CSV: 读取 {total_rows} 条，排除 {excluded_count} 条，保留 {len(papers)} 条")
    return papers


def merge_papers_two_sources(excel_papers: Dict[int, Dict[str, str]],
                             paper_list_papers: Dict[int, Dict[str, str]]) -> List[Dict[str, str]]:
    """合并两个数据源，字段优先级：Excel > paper-list"""

    # 收集所有 PID
    all_pids = set(excel_papers.keys()) | set(paper_list_papers.keys())

    merged = []

    for pid in sorted(all_pids):
        # 字段优先级：Excel > paper-list
        sources = [
            excel_papers.get(pid, {}),
            paper_list_papers.get(pid, {})
        ]

        # 合并字段（优先使用非空值）
        paper = {'编号': str(pid)}

        for field in ['期刊', '年份', '题目', '作者', '机构', '专家分类']:
            for source in sources:
                value = source.get(field, '').strip()
                if value:
                    paper[field] = value
                    break
            else:
                paper[field] = ''  # 所有数据源都没有，设为空

        merged.append(paper)

    return merged


def merge_papers(excel_papers: Dict[int, Dict[str, str]],
                 paper_list_papers: Dict[int, Dict[str, str]],
                 e2_paper_list_papers: Dict[int, Dict[str, str]]) -> List[Dict[str, str]]:
    """合并三个数据源，字段优先级：Excel > paper-list > e2-paper-list"""

    # 收集所有 PID
    all_pids = set(excel_papers.keys()) | set(paper_list_papers.keys()) | set(e2_paper_list_papers.keys())

    merged = []

    for pid in sorted(all_pids):
        # 字段优先级：Excel > paper-list > e2-paper-list
        sources = [
            excel_papers.get(pid, {}),
            paper_list_papers.get(pid, {}),
            e2_paper_list_papers.get(pid, {})
        ]

        # 合并字段（优先使用非空值）
        paper = {'编号': str(pid)}

        for field in ['期刊', '年份', '题目', '作者', '机构', '专家分类']:
            for source in sources:
                value = source.get(field, '').strip()
                if value:
                    paper[field] = value
                    break
            else:
                paper[field] = ''  # 所有数据源都没有，设为空

        merged.append(paper)

    return merged


def main():
    base_dir = Path(__file__).parent.parent
    results_dir = base_dir / 'results' / 'e2-top102'

    print("=" * 60)
    print("生成专家确认.csv")
    print("=" * 60)

    # 1. 读取排除列表
    print("\n[1/6] 读取排除列表...")

    # 1.1 专家纠正汇总中的所有 PID
    expert_corrections_file = results_dir / '专家纠正学科分类汇总.md'
    exclude_from_expert = load_expert_corrections(expert_corrections_file)
    print(f"      专家纠正汇总: {len(exclude_from_expert)} 个 PID")

    # 1.2 e2-paper-list.md 中的所有 PID
    print("      读取 e2-paper-list.md 中的所有 PID...")
    e2_paper_list_file = results_dir / 'e2-paper-list.md'
    content = e2_paper_list_file.read_text(encoding='utf-8')
    rows = parse_markdown_table(content)
    exclude_from_e2 = set()
    for row in rows:
        pid_str = row.get('PID', '').strip()
        if pid_str and pid_str.isdigit():
            exclude_from_e2.add(int(pid_str))
    print(f"      e2-paper-list.md: {len(exclude_from_e2)} 个 PID")

    # 合并排除列表
    exclude_pids = exclude_from_expert | exclude_from_e2
    print(f"      总排除数: {len(exclude_pids)} 个 PID")

    # 2. 读取 paper-list.md
    print("\n[2/4] 读取 paper-list.md...")
    paper_list_file = results_dir / 'paper-list.md'
    paper_list_papers = load_paper_list_md(paper_list_file, exclude_pids)

    # 3. 读取 Excel CSV
    print("\n[3/4] 读取 Excel CSV...")
    excel_csv_file = results_dir / '新分类修改版（未标黄）.csv'
    excel_papers = load_excel_csv(excel_csv_file, exclude_pids)

    # 4. 合并数据（只合并 paper-list 和 Excel，不使用 e2-paper-list）
    print("\n[4/4] 合并数据...")
    merged_papers = merge_papers_two_sources(excel_papers, paper_list_papers)
    print(f"✓ 合并后共 {len(merged_papers)} 条记录")

    # 6. 输出 CSV
    output_file = results_dir / '专家确认.csv'
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        fieldnames = ['编号', '期刊', '年份', '题目', '作者', '机构', '专家分类']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_papers)

    print(f"\n✅ 成功生成: {output_file}")
    print(f"   总记录数: {len(merged_papers)}")

    # 验证
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)

    # 检查是否有排除的 PID 残留
    result_pids = {int(p['编号']) for p in merged_papers}
    leaked = result_pids & exclude_pids
    if leaked:
        print(f"⚠️  警告: 以下 PID 应该被排除但仍在结果中: {sorted(leaked)}")
    else:
        print(f"✓ 所有需要排除的 PID ({len(exclude_pids)} 个) 都已正确移除")

    # 统计学科分布
    discipline_counts = {}
    for paper in merged_papers:
        disc = paper['专家分类']
        discipline_counts[disc] = discipline_counts.get(disc, 0) + 1

    print(f"\n学科分布:")
    for disc, count in sorted(discipline_counts.items(), key=lambda x: -x[1]):
        if disc:
            print(f"  {disc}: {count} 篇")

    empty_discipline_count = discipline_counts.get('', 0)
    if empty_discipline_count > 0:
        print(f"  ⚠️  学科为空: {empty_discipline_count} 篇")


if __name__ == '__main__':
    main()
