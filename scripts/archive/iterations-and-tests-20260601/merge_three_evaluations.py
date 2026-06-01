#!/usr/bin/env python3
"""合并三次评测结果，生成最终排名

逻辑：
- Tier 1 论文（10 篇）：保持原始 E1 分数不变
- 非选择性重测论文（7 篇，稳定）：取 E1 和 E2 的 R2 均分的均值
- 选择性重测论文（13 篇）：
  - 稳定维度（std ≤ 5）：取 E1 和 E2 的 R2 均分的均值
  - 不稳定维度（std > 5）：取 E1、E2、E3 的 R2 均分的中位数

输出：
- results/retest-top60/final_ranking_v2.json
- 追加到 results/retest-top60/top30_comparison.md

用法：
    python scripts/merge_three_evaluations.py
"""

import csv
import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.selective_retest_top30 import SELECTIVE_RETEST, DIM_ZH

# 维度权重
WEIGHTS = {
    'problem_originality': 0.30,
    'literature_insight': 0.20,
    'analytical_framework': 0.15,
    'logical_coherence': 0.20,
    'conclusion_consensus': 0.10,
    'forward_extension': 0.05,
}

DIM_KEYS = list(WEIGHTS.keys())

# Tier 1 论文 ID（直接入选，不重测）
TIER1_IDS = {1260, 1428, 1238, 1200, 1266, 946, 101, 1574, 820, 1764}

# 数据路径
E1_DIR = PROJECT_ROOT / "results" / "fullevaluation" / "round2"
E2_DIR = PROJECT_ROOT / "results" / "retest-top60" / "round2"
E3_DIR = PROJECT_ROOT / "results" / "retest-top60" / "round3" / "round2"
META_FILE = PROJECT_ROOT / "results" / "merged-metadata.csv"


def load_metadata():
    """加载论文元数据"""
    meta = {}
    with open(META_FILE, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            meta[int(r['编号'])] = r
    return meta


def load_eval_data(paper_id: int, eval_dir: Path) -> dict | None:
    """加载单次评测数据"""
    fpath = eval_dir / f"paper-{paper_id}.json"
    if not fpath.exists():
        return None
    with open(fpath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_r2_mean(eval_data: dict, dim_key: str) -> float | None:
    """提取某维度的 R2 均分"""
    if not eval_data:
        return None
    dim_data = eval_data.get('dimensions', {}).get(dim_key, {})
    return dim_data.get('round2_mean')


def get_r2_scores(eval_data: dict, dim_key: str) -> dict | None:
    """提取某维度的 R2 各模型分数"""
    if not eval_data:
        return None
    dim_data = eval_data.get('dimensions', {}).get(dim_key, {})
    return dim_data.get('round2_scores')


def compute_dim_std_8scores(e1_data, e2_data, dim_key):
    """计算两次评测 R2 合并的 8 分数 std"""
    s1 = get_r2_scores(e1_data, dim_key)
    s2 = get_r2_scores(e2_data, dim_key)
    if not s1 or not s2:
        return 0
    all_scores = list(s1.values()) + list(s2.values())
    return statistics.stdev(all_scores) if len(all_scores) > 1 else 0


def compute_final_dim_scores(paper_id: int, e1_data, e2_data, e3_data) -> dict:
    """计算最终各维度分数

    返回: {dim_key: {'final_score': float, 'source': str, 'e1_mean': float, 'e2_mean': float, 'e3_mean': float|None}}
    """
    target_dims = SELECTIVE_RETEST.get(paper_id, [])
    result = {}

    for dk in DIM_KEYS:
        e1_mean = get_r2_mean(e1_data, dk)
        e2_mean = get_r2_mean(e2_data, dk)
        e3_mean = get_r2_mean(e3_data, dk) if e3_data else None

        if dk in target_dims and e3_mean is not None:
            # 不稳定维度：三次中位数
            final = statistics.median([e1_mean, e2_mean, e3_mean])
            source = "median(E1,E2,E3)"
        elif e1_mean is not None and e2_mean is not None:
            # 稳定维度或无 E3 数据：两次均值
            final = (e1_mean + e2_mean) / 2
            source = "mean(E1,E2)"
        elif e1_mean is not None:
            # 仅有 E1（Tier 1 论文）
            final = e1_mean
            source = "E1 only"
        else:
            final = 0
            source = "missing"

        result[dk] = {
            'final_score': round(final, 1),
            'source': source,
            'e1_mean': e1_mean,
            'e2_mean': e2_mean,
            'e3_mean': e3_mean,
        }

    return result


def compute_weighted_total(dim_scores: dict) -> float:
    """计算加权总分"""
    total = sum(
        dim_scores[dk]['final_score'] * WEIGHTS[dk]
        for dk in DIM_KEYS
        if dk in dim_scores
    )
    return round(total, 2)


def compute_dim_std_final(dim_scores: dict, e1_data, e2_data, e3_data, dim_key: str) -> float:
    """计算最终维度的 std

    对不稳定维度（有 E3），合并三次 R2 分数（12 个）
    对稳定维度，合并两次 R2 分数（8 个）
    """
    scores = []
    s1 = get_r2_scores(e1_data, dim_key)
    s2 = get_r2_scores(e2_data, dim_key)
    s3 = get_r2_scores(e3_data, dim_key) if e3_data else None

    if s1:
        scores.extend(s1.values())
    if s2:
        scores.extend(s2.values())
    if s3:
        scores.extend(s3.values())

    return round(statistics.stdev(scores), 1) if len(scores) > 1 else 0


def get_top60_ids():
    """获取 Top 60 论文 ID 列表（按第二次评测排名）"""
    ranking_file = PROJECT_ROOT / "results" / "retest-top60" / "final_ranking.json"
    with open(ranking_file, 'r', encoding='utf-8') as f:
        ranking = json.load(f)
    return [p['paper_id'] for p in ranking['all_papers'][:60]]


def main():
    meta = load_metadata()
    top60_ids = get_top60_ids()

    print("合并三次评测结果...")
    print(f"Top 60 论文数: {len(top60_ids)}")

    all_results = []

    for pid in top60_ids:
        m = meta.get(pid, {})
        e1_data = load_eval_data(pid, E1_DIR)
        e2_data = load_eval_data(pid, E2_DIR)
        e3_data = load_eval_data(pid, E3_DIR)

        is_tier1 = pid in TIER1_IDS
        is_selective = pid in SELECTIVE_RETEST

        if is_tier1:
            # Tier 1: 仅用 E1
            dim_scores = {}
            for dk in DIM_KEYS:
                e1_mean = get_r2_mean(e1_data, dk) if e1_data else 0
                dim_scores[dk] = {
                    'final_score': round(e1_mean, 1) if e1_mean else 0,
                    'source': 'E1 only (Tier 1)',
                    'e1_mean': e1_mean,
                    'e2_mean': None,
                    'e3_mean': None,
                }
        else:
            dim_scores = compute_final_dim_scores(pid, e1_data, e2_data, e3_data)

        total_score = compute_weighted_total(dim_scores)

        # 计算 std
        dim_stds = {}
        for dk in DIM_KEYS:
            dim_stds[dk] = compute_dim_std_final(dim_scores, e1_data, e2_data, e3_data, dk)

        avg_std = round(statistics.mean(dim_stds.values()), 2) if dim_stds else 0

        # E2 排名中的总分（用于对比）
        e2_total = None
        if not is_tier1 and e2_data:
            e2_dim_scores = {}
            for dk in DIM_KEYS:
                e1m = get_r2_mean(e1_data, dk)
                e2m = get_r2_mean(e2_data, dk)
                if e1m is not None and e2m is not None:
                    e2_dim_scores[dk] = {'final_score': round((e1m + e2m) / 2, 1)}
                elif e1m is not None:
                    e2_dim_scores[dk] = {'final_score': round(e1m, 1)}
                else:
                    e2_dim_scores[dk] = {'final_score': 0}
            e2_total = compute_weighted_total(e2_dim_scores)

        result = {
            'paper_id': pid,
            'title': m.get('题目', ''),
            'year': m.get('年份', ''),
            'journal': m.get('期刊', ''),
            'author': m.get('作者', ''),
            'institution': m.get('作者机构', ''),
            'total_score': total_score,
            'e2_total_score': e2_total,
            'delta3': round(total_score - e2_total, 2) if e2_total else None,
            'avg_std': avg_std,
            'dim_scores': dim_scores,
            'dim_stds': dim_stds,
            'is_tier1': is_tier1,
            'is_selective': is_selective,
        }
        all_results.append(result)

    # 排序
    all_results.sort(key=lambda x: -x['total_score'])

    # 输出 JSON
    ranking = {
        "generated_at": str(__import__('datetime').datetime.now()),
        "method": "三次评测中位数（不稳定维度）+ 两次均值（稳定维度）",
        "top30": [],
        "all_papers": [],
    }

    for i, r in enumerate(all_results[:60]):
        entry = {
            "rank": i + 1,
            "paper_id": r['paper_id'],
            "title": r['title'],
            "total_score": r['total_score'],
            "delta3": r['delta3'],
            "avg_std": r['avg_std'],
            "is_tier1": r['is_tier1'],
            "is_selective": r['is_selective'],
        }
        ranking["all_papers"].append(entry)
        if i < 30:
            ranking["top30"].append(entry)

    output_file = PROJECT_ROOT / "results" / "retest-top60" / "final_ranking_v2.json"
    output_file.write_text(
        json.dumps(ranking, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    print(f"\n✅ 排名已保存到 {output_file}")

    # 生成 Markdown 追加内容
    generate_markdown(all_results, meta)


def generate_markdown(all_results: list, meta: dict):
    """生成 Markdown 内容追加到 top30_comparison.md"""
    top30 = all_results[:30]

    lines = []
    lines.append("")
    lines.append("## 第三次评测 Top 30（三次 R2 中位数，含 Tier 1）")
    lines.append("")
    lines.append("★ = Tier 1 直接入选 | ◆ = 选择性第 3 次评测（不稳定维度取三次中位数）")
    lines.append("")

    # 表头
    header = "| # | 题目 | 年份 | 刊物 | 作者 | 机构 | ID | 总分 | Δ3 | std | 创新性 | 洞察度 | 建构力 | 连贯性 | 共识度 | 延展性 | s创新 | s洞察 | s建构 | s连贯 | s共识 | s延展 |"
    sep = "|---|------|------|------|------|------|-----|------|-----|-----|--------|--------|--------|--------|--------|--------|-------|-------|-------|-------|-------|-------|"
    lines.append(header)
    lines.append(sep)

    for i, r in enumerate(top30):
        rank = i + 1
        if r['is_tier1']:
            rank_str = f"★{rank}"
        elif r['is_selective']:
            rank_str = f"◆{rank}"
        else:
            rank_str = f"  {rank}"

        delta3_str = f"{r['delta3']:+.2f}" if r['delta3'] is not None else "—"

        # 维度分数
        dim_strs = []
        for dk in DIM_KEYS:
            ds = r['dim_scores'].get(dk, {})
            dim_strs.append(f"{ds.get('final_score', 0):.1f}")

        # 维度 std
        std_strs = []
        for dk in DIM_KEYS:
            std_strs.append(f"{r['dim_stds'].get(dk, 0):.1f}")

        author = r.get('author', '')
        inst = r.get('institution', '')[:20] + '..' if len(r.get('institution', '')) > 20 else r.get('institution', '')

        line = (
            f"| {rank_str} | {r['title'][:40]} | {r['year']} | {r['journal']} | "
            f"{author} | {inst} | {r['paper_id']} | {r['total_score']:.2f} | {delta3_str} | "
            f"{r['avg_std']:.2f} | "
            f"{dim_strs[0]} | {dim_strs[1]} | {dim_strs[2]} | {dim_strs[3]} | {dim_strs[4]} | {dim_strs[5]} | "
            f"{std_strs[0]} | {std_strs[1]} | {std_strs[2]} | {std_strs[3]} | {std_strs[4]} | {std_strs[5]} |"
        )
        lines.append(line)

    # 排名变化对比
    lines.append("")
    lines.append("## 第三次评测排名变化对比")
    lines.append("")

    # 找出排名变化
    prev_top30_ids = set()
    ranking_file = PROJECT_ROOT / "results" / "retest-top60" / "final_ranking.json"
    if ranking_file.exists():
        with open(ranking_file, 'r', encoding='utf-8') as f:
            prev_ranking = json.load(f)
        prev_top30_ids = set(p['paper_id'] for p in prev_ranking.get('all_papers', [])[:30])

    curr_top30_ids = set(r['paper_id'] for r in top30)

    new_entries = curr_top30_ids - prev_top30_ids
    dropped = prev_top30_ids - curr_top30_ids

    if new_entries:
        lines.append("### 新进入 Top 30（第三次评测后）")
        lines.append("")
        for pid in new_entries:
            r = next(x for x in all_results if x['paper_id'] == pid)
            # 找之前的排名
            prev_rank = "?"
            if ranking_file.exists():
                for j, p in enumerate(prev_ranking.get('all_papers', [])):
                    if p['paper_id'] == pid:
                        prev_rank = str(j + 1)
                        break
            lines.append(f"- **{r['title']}** (ID={pid}): 原#{prev_rank} → 现#{top30.index(r) + 1}，总分 {r['total_score']:.2f} (Δ3={r['delta3']:+.2f})" if r['delta3'] else f"- **{r['title']}** (ID={pid}): 原#{prev_rank} → 现#{top30.index(r) + 1}，总分 {r['total_score']:.2f}")
        lines.append("")

    if dropped:
        lines.append("### 跌出 Top 30（第三次评测后）")
        lines.append("")
        for pid in dropped:
            r = next((x for x in all_results if x['paper_id'] == pid), None)
            if r:
                curr_rank = next((j + 1 for j, x in enumerate(all_results) if x['paper_id'] == pid), "?")
                lines.append(f"- **{r['title']}** (ID={pid}): 现#{curr_rank}，总分 {r['total_score']:.2f}")
        lines.append("")

    # 排名变化最大的论文
    lines.append("### 排名变化最大的论文（选择性重测）")
    lines.append("")
    lines.append("| ID | 题目 | 第二次排名 | 第三次排名 | 变化 | Δ3分 | 变化原因 |")
    lines.append("|-----|------|-----------|-----------|------|------|---------|")

    changes = []
    for r in all_results:
        if not r['is_selective']:
            continue
        pid = r['paper_id']
        # 找第二次排名
        prev_rank = None
        if ranking_file.exists():
            for j, p in enumerate(prev_ranking.get('all_papers', [])):
                if p['paper_id'] == pid:
                    prev_rank = j + 1
                    break
        curr_rank = next((j + 1 for j, x in enumerate(all_results) if x['paper_id'] == pid), None)
        if prev_rank and curr_rank:
            rank_change = prev_rank - curr_rank  # 正数=上升
            changes.append({
                'paper': r,
                'prev_rank': prev_rank,
                'curr_rank': curr_rank,
                'rank_change': rank_change,
            })

    changes.sort(key=lambda x: -abs(x['rank_change']))
    for c in changes[:10]:
        r = c['paper']
        pid = r['paper_id']
        change_str = f"{'↑' if c['rank_change'] > 0 else '↓'}{abs(c['rank_change'])}" if c['rank_change'] != 0 else "—"

        # 找出变化原因：哪个维度的第 3 次评测导致了变化
        reasons = []
        target_dims = SELECTIVE_RETEST.get(pid, [])
        for dk in target_dims:
            ds = r['dim_scores'].get(dk, {})
            if ds.get('e3_mean') is not None:
                e3 = ds['e3_mean']
                prev = (ds.get('e1_mean', 0) + ds.get('e2_mean', 0)) / 2 if ds.get('e1_mean') and ds.get('e2_mean') else 0
                diff = e3 - prev
                if abs(diff) > 2:
                    reasons.append(f"{DIM_ZH.get(dk, dk)}: E3={e3:.1f}(vs均值{prev:.1f},Δ={diff:+.1f})")

        reason_str = "; ".join(reasons) if reasons else "变化较小"
        delta3_str = f"{r['delta3']:+.2f}" if r['delta3'] else "—"

        lines.append(
            f"| {pid} | {r['title'][:30]} | #{c['prev_rank']} | #{c['curr_rank']} | "
            f"{change_str} | {delta3_str} | {reason_str} |"
        )

    lines.append("")

    # 仍异常的论文
    lines.append("### 仍标记为异常的论文（三次 std 仍 > 5）")
    lines.append("")
    lines.append("以下论文的第 3 次评测后仍有维度 std > 5，建议专家复核：")
    lines.append("")
    lines.append("| ID | 题目 | 异常维度 | 三次 std | 建议 |")
    lines.append("|-----|------|---------|---------|------|")

    has_remaining = False
    for r in all_results[:30]:
        if not r['is_selective']:
            continue
        for dk in DIM_KEYS:
            std_val = r['dim_stds'].get(dk, 0)
            if std_val > 5:
                has_remaining = True
                lines.append(
                    f"| {r['paper_id']} | {r['title'][:30]} | {DIM_ZH.get(dk, dk)} | {std_val:.1f} | 专家复核 |"
                )

    if not has_remaining:
        lines.append("| — | 无 | — | — | ✅ 所有维度已收敛 |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**生成时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}")
    lines.append("**计分方式**: 不稳定维度取三次 R2 均分的中位数，稳定维度取两次 R2 均分的均值")
    lines.append(f"**数据来源**: E1=`results/fullevaluation/round2/`, E2=`results/retest-top60/round2/`, E3=`results/retest-top60/round3/round2/`")

    md_content = "\n".join(lines)

    # 追加到 top30_comparison.md
    comparison_file = PROJECT_ROOT / "results" / "retest-top60" / "top30_comparison.md"
    with open(comparison_file, 'a', encoding='utf-8') as f:
        f.write("\n" + md_content)

    print(f"✅ 已追加到 {comparison_file}")

    # 同时输出到 round3 目录
    round3_dir = PROJECT_ROOT / "results" / "retest-top60" / "round3"
    round3_dir.mkdir(parents=True, exist_ok=True)
    (round3_dir / "evaluation_changes.md").write_text(md_content, encoding='utf-8')
    print(f"✅ 详细报告已保存到 {round3_dir / 'evaluation_changes.md'}")


if __name__ == "__main__":
    main()
