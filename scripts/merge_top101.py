#!/usr/bin/env python3
"""合并 101 篇 E2 论文的 E1/E2/E3 数据到统一目录

数据源：
  E1: results/top101/E1/paper-{id}.json（101 篇）
  E2: results/top101/E2/paper-{id}.json（101 篇）
  E3: results/top101/E3/paper-{id}.json（45 篇选择性维度）

聚合规则：
  - 单源（仅 E1）：mean（4 个模型分数）
  - 双源（E1+E2）：median（8 个模型分数）
  - 三源（E1+E2+E3）：median（E3 选择性维度叠加到 12 个分数）

输出：
  results/top101/paper-{id}.json    每篇合并后的自包含结果
  results/top101/ranking.json       101 篇完整排名
  results/top101/top50.json         纯分数 Top50 诊断输出（非当前 PPT 真源）

用法：
    python3 scripts/merge_top101.py
"""

import csv
import json
import os
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODELS = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
WEIGHTS = {
    'problem_originality': 0.30,
    'literature_insight': 0.20,
    'analytical_framework': 0.15,
    'logical_coherence': 0.20,
    'conclusion_consensus': 0.10,
    'forward_extension': 0.05,
}
DIM_ZH = {
    'problem_originality': '研究创新性',
    'literature_insight': '现状洞察度',
    'analytical_framework': '理论建构力',
    'logical_coherence': '逻辑连贯性',
    'conclusion_consensus': '学术共识度',
    'forward_extension': '前瞻延展性',
}

# 数据源目录（统一从 results/top101/ 下的 E1/E2/E3 读取）
SOURCES = {
    'E1': ['results/top101/E1'],
    'E2': ['results/top101/E2'],
    'E3': ['results/top101/E3'],
}


def paper_ids_from_source(source_name):
    """Return paper IDs materialized under a Top101 source directory."""
    ids = set()
    for directory in SOURCES[source_name]:
        source_dir = PROJECT_ROOT / directory
        if not source_dir.exists():
            continue
        for path in source_dir.glob("paper-*.json"):
            try:
                ids.add(int(path.stem.removeprefix("paper-")))
            except ValueError:
                continue
    return ids


def candidate_paper_ids():
    """Load the current E2 candidate pool.

    The materialized E2 directory is the source of truth for the current
    101-paper candidate pool. Historical selection files are local provenance
    artifacts and are not used by this active merge script.
    """
    e2_ids = paper_ids_from_source('E2')
    if len(e2_ids) == 101:
        return sorted(e2_ids)

    raise FileNotFoundError(
        f"results/top101/E2/ 当前有 {len(e2_ids)} 篇，"
        "必须为 101 篇才能重生 Top101 ranking。"
    )


def load_r2_scores(directories, pid):
    """从多个目录中加载某篇论文的 R2 scores"""
    for d in directories:
        path = os.path.join(PROJECT_ROOT, d, f"paper-{pid}.json")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = {}
            for dk, dd in data.get('dimensions', {}).items():
                r2 = dd.get('round2_scores', {})
                if r2:
                    result[dk] = dict(r2)  # {model: score}
            return result, data
    return None, None


def pool_dimension_scores(e1_scores, e2_scores, e3_scores, dim_key):
    """
    合并单个维度的多轮分数池
    返回 (pooled_scores: list[float], sources: list[str])
    """
    pools = []
    sources = []

    if e1_scores and dim_key in e1_scores:
        pools.extend(e1_scores[dim_key].values())
        sources.append('E1')
    if e2_scores and dim_key in e2_scores:
        pools.extend(e2_scores[dim_key].values())
        sources.append('E2')
    if e3_scores and dim_key in e3_scores:
        pools.extend(e3_scores[dim_key].values())
        sources.append('E3')

    return pools, sources


def aggregate_pool(pools, sources):
    """根据源数量选择聚合方法"""
    if not pools:
        return None, None, None

    n_sources = len(set(sources))
    if n_sources >= 2:
        # 多源 → 中位数（更鲁棒）
        return round(statistics.median(pools), 4), 'median', len(pools)
    else:
        # 单源 → 均值
        return round(statistics.mean(pools), 4), 'mean', len(pools)


def main():
    # ── 1. 确定 101 篇 PID ──
    all101 = candidate_paper_ids()
    print(f"101 篇论文 PID: {len(all101)} 篇")

    # ── 2. 读取元数据 ──
    meta = {}
    with open(PROJECT_ROOT / 'results' / 'merged-metadata.csv',
              'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            meta[int(row['编号'])] = row

    # ── 3. 创建输出目录 ──
    out_dir = PROJECT_ROOT / 'results' / 'top101'
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 4. 逐篇合并 ──
    all_papers = []
    source_counts = {'E1': 0, 'E1+E2': 0, 'E1+E3': 0, 'E1+E2+E3': 0}

    for pid in all101:
        # 加载各轮数据
        e1_scores, e1_raw = load_r2_scores(SOURCES['E1'], pid)
        e2_scores, e2_raw = load_r2_scores(SOURCES['E2'], pid)
        e3_scores, e3_raw = load_r2_scores(SOURCES['E3'], pid)

        has_e2 = e2_scores is not None
        has_e3 = e3_scores is not None

        # 确定来源标签
        parts = ['E1']
        if has_e2:
            parts.append('E2')
        if has_e3:
            parts.append('E3')
        source_label = '+'.join(parts)
        source_counts[source_label] = source_counts.get(source_label, 0) + 1

        # 逐维度聚合
        dimensions = {}
        for dk in WEIGHTS:
            pools, sources = pool_dimension_scores(
                e1_scores, e2_scores, e3_scores, dk
            )
            if not pools:
                continue

            avg, method, n = aggregate_pool(pools, sources)
            std = round(statistics.stdev(pools), 2) if len(pools) >= 2 else 0

            # 收集各轮原始分数用于追溯
            round_scores = {}
            if e1_scores and dk in e1_scores:
                round_scores['E1'] = e1_scores[dk]
            if e2_scores and dk in e2_scores:
                round_scores['E2'] = e2_scores[dk]
            if e3_scores and dk in e3_scores:
                round_scores['E3'] = e3_scores[dk]

            dimensions[dk] = {
                'dimension': dk,
                'name_zh': DIM_ZH[dk],
                'pooled_avg': avg,
                'pooled_std': std,
                'pooled_n': n,
                'method': f"{method}({n}) [{'+'.join(sources)}]",
                'round_scores': round_scores,
            }

        # 加权总分
        weighted = sum(WEIGHTS[dk] * dimensions[dk]['pooled_avg']
                       for dk in WEIGHTS if dk in dimensions)
        weighted_std = sum(WEIGHTS[dk] * dimensions[dk]['pooled_std']
                           for dk in WEIGHTS if dk in dimensions)

        # 元数据
        m = meta.get(pid, {})

        paper_result = {
            'pid': pid,
            'source': source_label,
            'weighted_score': round(weighted, 4),
            'weighted_std': round(weighted_std, 2),
            'dimensions': dimensions,
            'metadata': {
                'title': m.get('题目', ''),
                'category': m.get('分类', ''),
                'journal': m.get('期刊', ''),
                'year': m.get('年份', ''),
                'volume': m.get('卷', ''),
                'issue': m.get('期', ''),
                'author': m.get('作者', ''),
                'institution': m.get('作者机构', ''),
                'pages': m.get('页数', ''),
            },
        }
        all_papers.append(paper_result)

        # 写单篇合并文件
        paper_path = out_dir / f"paper-{pid}.json"
        paper_path.write_text(
            json.dumps(paper_result, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )

    # ── 5. 排序 ──
    all_papers.sort(key=lambda x: x['weighted_score'], reverse=True)
    for i, p in enumerate(all_papers, 1):
        p['rank'] = i

    # ── 6. 输出排名 ──
    ranking = {
        'metadata': {
            'description': 'Top 101 E2 论文 — E1+E2+E3 pooled aggregation',
            'total': len(all_papers),
            'weights': WEIGHTS,
            'aggregation_rule': '单源→mean; 双源→median; 三源→median',
            'source_distribution': source_counts,
        },
        'papers': all_papers,
    }
    (out_dir / 'ranking.json').write_text(
        json.dumps(ranking, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    # Top 50
    top50 = {
        'metadata': ranking['metadata'],
        'papers': all_papers[:50],
    }
    (out_dir / 'top50.json').write_text(
        json.dumps(top50, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    # ── 7. 打印汇总 ──
    print(f"\n{'='*70}")
    print(f"合并完成 → results/top101/")
    print(f"{'='*70}")
    print(f"单篇文件: {len(all_papers)} 个")
    print(f"数据来源分布:")
    for s, c in sorted(source_counts.items()):
        print(f"  {s}: {c} 篇")
    print(f"\n排名文件: ranking.json, top50.json")

    print(f"\n{'─'*70}")
    print(f"Top 50 排名（E1+E2+E3 中位数聚合）")
    print(f"{'─'*70}")
    print(f"{'#':>3} {'PID':>5} {'分数':>6} {'Std':>5} {'来源':>10} "
          f"{'领域':>14} {'期刊':>10} {'年份':>5} 题目")
    print(f"{'─'*70}")

    for p in all_papers[:50]:
        m = p['metadata']
        title = m['title'][:38] + ('…' if len(m['title']) > 38 else '')
        cat = m['category']
        if len(cat) > 10:
            cat = cat[:10] + '…'
        print(f"{p['rank']:>3} {p['pid']:>5} {p['weighted_score']:>6.2f} "
              f"{p['weighted_std']:>5.2f} {p['source']:>10} "
              f"{cat:>14} {m['journal']:>10} {m['year']:>5} {title}")


if __name__ == '__main__':
    main()
