#!/usr/bin/env python3
"""
Unified scoring: merge E1/E2/E3 data layers into a single ranking.

Aggregation strategy:
  - E1 only (4 models):  mean  — 充分利用 4 个模型信息
  - E1+E2 pooled (8 scores): median — 跨评测池化，天然抗极端值
  - E1+E3 pooled (8 scores): median — 同上（仅 target dims）
  - E1+E2+E3 pooled (12 scores): median — 3 次评测池化

Pipeline:
  E1 R2 (baseline, all papers)
  → E2 R2 (pool with E1, all 6 dims, 26 papers)
  → E3 R2 (pool with existing, target_dims only, 13 papers)

Weights (v2.55):
  创新性 0.30 + 洞察度 0.20 + 建构力 0.15 + 连贯性 0.20 + 共识度 0.10 + 延展性 0.05

Output: results/unified_rankings.json
"""

import json
import os
import statistics
from pathlib import Path


WEIGHTS = {
    'problem_originality': 0.30,
    'literature_insight': 0.20,
    'analytical_framework': 0.15,
    'logical_coherence': 0.20,
    'conclusion_consensus': 0.10,
    'forward_extension': 0.05,
}

DIMS = list(WEIGHTS.keys())


def load_paper_scores(json_path: Path) -> dict | None:
    """Load dimension round2_scores from a paper JSON file.

    Returns raw scores per dimension (model_name → score).
    """
    if not json_path.exists():
        return None
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}
    dims_data = data.get('dimensions', {})
    for dim in DIMS:
        dim_info = dims_data.get(dim, {})
        r2_scores = dim_info.get('round2_scores', {})
        vals = [v for v in r2_scores.values() if isinstance(v, (int, float))]
        result[dim] = {
            'scores': r2_scores,
            'vals': vals,
        }
    return result


def aggregate(vals: list) -> tuple:
    """Aggregate a list of scores.

    - 4 scores (E1 only): mean
    - 8+ scores (pooled): median (robust to outlier models)

    Returns (avg, std, n, method).
    """
    if not vals:
        return 0.0, 0.0, 0, 'none'
    n = len(vals)
    std = statistics.stdev(vals) if n > 1 else 0.0
    if n <= 4:
        return statistics.mean(vals), std, n, 'mean'
    else:
        return statistics.median(vals), std, n, 'median'


def calc_weighted_score(dim_data: dict) -> float:
    """Calculate weighted total score."""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += dim_data[dim]['avg'] * weight
    return total


def calc_weighted_std(dim_data: dict) -> float:
    """Calculate weighted std (weighted average of dimension stds)."""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += dim_data[dim]['std'] * weight
    return total


def main():
    e1_dir = Path('results/fullevaluation/round2')
    e2_dir = Path('results/retest-top71-supplement/e2/round2')
    e3_dir = Path('results/retest-top71-supplement/e3/round2')

    # ── Step 1: Load E1 baseline ──
    print('Loading E1 R2 baseline...')
    all_scores = {}
    e1_files = sorted(e1_dir.glob('paper-*.json'))
    for f in e1_files:
        pid = int(f.stem.replace('paper-', ''))
        raw = load_paper_scores(f)
        if raw:
            # E1 only: aggregate with mean
            dim_data = {}
            for dim in DIMS:
                vals = raw[dim]['vals']
                avg, std, n, method = aggregate(vals)
                dim_data[dim] = {
                    'avg': avg,
                    'std': std,
                    'n': n,
                    'method': method,
                    'pooled_vals': vals,  # keep for potential E2/E3 pooling
                }
            all_scores[pid] = {
                'source': 'E1',
                'dims': dim_data,
                'e2_override': False,
                'e3_merged': [],
            }
    print(f'  E1: {len(all_scores)} papers loaded')

    # ── Step 2: Pool E2 with E1 ──
    print('Pooling E2 R2 with E1...')
    e2_count = 0
    if e2_dir.exists():
        e2_files = sorted(e2_dir.glob('paper-*.json'))
        for f in e2_files:
            pid = int(f.stem.replace('paper-', ''))
            raw = load_paper_scores(f)
            if raw and pid in all_scores:
                for dim in DIMS:
                    # Pool E1 vals + E2 vals
                    e1_vals = all_scores[pid]['dims'][dim]['pooled_vals']
                    e2_vals = raw[dim]['vals']
                    pooled = e1_vals + e2_vals
                    avg, std, n, method = aggregate(pooled)
                    all_scores[pid]['dims'][dim] = {
                        'avg': avg,
                        'std': std,
                        'n': n,
                        'method': method,
                        'pooled_vals': pooled,
                    }
                all_scores[pid]['source'] = 'E1+E2'
                all_scores[pid]['e2_override'] = True
                e2_count += 1
    print(f'  E2: {e2_count} papers pooled')

    # ── Step 3: Pool E3 with existing (E1 or E1+E2) for target dims ──
    print('Pooling E3 R2 selective dimensions...')
    e3_count = 0
    if e3_dir.exists():
        e3_files = sorted(e3_dir.glob('paper-*.json'))
        for f in e3_files:
            pid = int(f.stem.replace('paper-', ''))
            if pid not in all_scores:
                continue
            with open(f, 'r', encoding='utf-8') as fh:
                e3_data = json.load(fh)

            target_dims = e3_data.get('target_dims', [])
            dims_data = e3_data.get('dimensions', {})
            merged = []

            for dim in target_dims:
                if dim not in dims_data:
                    continue
                r2_scores = dims_data[dim].get('round2_scores', {})
                e3_vals = [v for v in r2_scores.values() if isinstance(v, (int, float))]
                if e3_vals:
                    # Pool with existing (E1 only or E1+E2)
                    existing_vals = all_scores[pid]['dims'][dim]['pooled_vals']
                    pooled = existing_vals + e3_vals
                    avg, std, n, method = aggregate(pooled)
                    all_scores[pid]['dims'][dim] = {
                        'avg': avg,
                        'std': std,
                        'n': n,
                        'method': method,
                        'pooled_vals': pooled,
                    }
                    merged.append(dim)

            if merged:
                all_scores[pid]['e3_merged'] = merged
                if all_scores[pid]['e2_override']:
                    all_scores[pid]['source'] = 'E1+E2+E3'
                else:
                    all_scores[pid]['source'] = 'E1+E3'
                e3_count += 1
    print(f'  E3: {e3_count} papers merged')

    # ── Step 4: Calculate final scores ──
    print('Calculating unified scores...')
    results = []
    for pid, info in all_scores.items():
        ws = calc_weighted_score(info['dims'])
        wstd = calc_weighted_std(info['dims'])

        dim_avgs = {}
        dim_stds = {}
        dim_methods = {}
        for dim in DIMS:
            dim_avgs[dim] = round(info['dims'][dim]['avg'], 2)
            dim_stds[dim] = round(info['dims'][dim]['std'], 2)
            dim_methods[dim] = f"{info['dims'][dim]['method']}({info['dims'][dim]['n']})"

        results.append({
            'pid': pid,
            'weighted_score': round(ws, 3),
            'weighted_std': round(wstd, 2),
            'dim_avgs': dim_avgs,
            'dim_stds': dim_stds,
            'dim_methods': dim_methods,
            'source': info['source'],
            'e2_override': info['e2_override'],
            'e3_merged': info['e3_merged'],
        })

    # Sort by weighted score descending
    results.sort(key=lambda x: x['weighted_score'], reverse=True)

    # Add rank
    for i, r in enumerate(results, 1):
        r['rank'] = i

    # Summary
    top30 = results[:30]
    top60 = results[:60]

    source_counts = {}
    for r in top30:
        s = r['source']
        source_counts[s] = source_counts.get(s, 0) + 1

    print(f'\nUnified rankings generated: {len(results)} papers')
    print(f'Top 30 source breakdown: {source_counts}')
    print(f'Top 30 score range: {top30[-1]["weighted_score"]:.2f} - {top30[0]["weighted_score"]:.2f}')
    print(f'Top 60 score range: {top60[-1]["weighted_score"]:.2f} - {top60[0]["weighted_score"]:.2f}')

    # Output
    output = {
        'metadata': {
            'description': 'Unified E1/E2/E3 scoring (pooled aggregation)',
            'pipeline': 'E1 R2 baseline → E2 R2 pool → E3 R2 selective pool',
            'aggregation': 'E1 only: mean(4); E1+E2: median(8); E1+E2+E3: median(12)',
            'weights': WEIGHTS,
            'total_papers': len(results),
            'e2_pooled': e2_count,
            'e3_pooled': e3_count,
        },
        'all_papers': results,
        'top30': top30,
        'top60': top60,
    }

    out_path = Path('results/unified_rankings.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nSaved to: {out_path}')

    # Print Top 30
    print(f'\n{"Rank":>4} {"PID":>6} {"Score":>7} {"Std":>5} {"Source":>10} {"Title"}')
    print('-' * 85)

    # Load metadata for titles
    meta = {}
    csv_path = Path('results/merged-metadata.csv')
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            import csv
            for row in csv.DictReader(f):
                meta[int(row['编号'])] = row['题目']

    for r in top30:
        title = meta.get(r['pid'], f'Paper {r["pid"]}')[:40]
        print(f'{r["rank"]:>4} {r["pid"]:>6} {r["weighted_score"]:>7.2f} {r["weighted_std"]:>5.2f} {r["source"]:>10} {title}')


if __name__ == '__main__':
    main()
