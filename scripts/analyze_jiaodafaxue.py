#!/usr/bin/env python3
"""交大法学 642 篇评价结果统计总结"""
import json, os, statistics
from collections import defaultdict

RESULTS_DIR = "results/jiaodafaxue-evaluation/round2"
PAPER_LIST = "results/jiaodafaxue-paper-list.json"

with open(PAPER_LIST, 'r', encoding='utf-8') as f:
    paper_meta = json.load(f)

# Load only needed fields from results (skip raw_outputs for speed)
results = {}
for fname in sorted(os.listdir(RESULTS_DIR)):
    if not fname.startswith('paper-') or not fname.endswith('.json'):
        continue
    pid = int(fname.replace('paper-', '').replace('.json', ''))
    with open(os.path.join(RESULTS_DIR, fname), 'r', encoding='utf-8') as f:
        data = json.load(f)
    results[pid] = data

dim_keys = ['problem_originality', 'current_awareness', 'theoretical_construction',
            'logical_coherence', 'academic_consensus', 'forward_extension']
dim_zh = {
    'problem_originality': '研究创新性',
    'current_awareness': '现状洞察度',
    'theoretical_construction': '理论建构力',
    'logical_coherence': '逻辑连贯性',
    'academic_consensus': '学术共识度',
    'forward_extension': '前瞻延展性'
}

# Per-paper stats
paper_stats = []
dim_r1_scores = defaultdict(list)
dim_r2_scores = defaultdict(list)
dim_r1_stds = defaultdict(list)
dim_r2_stds = defaultdict(list)

for pid, res in sorted(results.items()):
    dims = res.get('dimensions', {})
    r1_scores, r2_scores, r1_stds, r2_stds = [], [], [], []
    for dk in dim_keys:
        d = dims.get(dk, {})
        r1 = d.get('round1_scores', {})
        r2 = d.get('round2_scores', {})
        r1_vals = [v for v in r1.values() if isinstance(v, (int, float))]
        r2_vals = [v for v in r2.values() if isinstance(v, (int, float))]
        if r1_vals:
            r1_std = statistics.stdev(r1_vals) if len(r1_vals) > 1 else 0
            dim_r1_scores[dk].extend(r1_vals)
            dim_r1_stds[dk].append(r1_std)
            r1_scores.extend(r1_vals)
            r1_stds.append(r1_std)
        if r2_vals:
            r2_std = statistics.stdev(r2_vals) if len(r2_vals) > 1 else 0
            dim_r2_scores[dk].extend(r2_vals)
            dim_r2_stds[dk].append(r2_std)
            r2_scores.extend(r2_vals)
            r2_stds.append(r2_std)
    if r1_scores and r2_scores:
        paper_stats.append({
            'id': pid,
            'r1_avg': statistics.mean(r1_scores),
            'r2_avg': statistics.mean(r2_scores),
            'r1_avg_std': statistics.mean(r1_stds),
            'r2_avg_std': statistics.mean(r2_stds),
            'r1_max_std': max(r1_stds),
            'r2_max_std': max(r2_stds),
            'filename': res.get('paper', ''),
        })

# === Output ===
out = []
def p(s=""):
    out.append(s)

p("# 交大法学评价统计总结")
p()
p("## 基本信息")
p(f"- 期刊：交大法学")
p(f"- 总论文数：{paper_meta['total']}")
p(f"- 成功评价：{len(paper_stats)} 篇（R1 失败 1 篇）")
p(f"- 评价框架：law-v2.55（交叉评审版本）")
p(f"- 评价模型：4 个（deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus）")
p(f"- 总耗时：约 20 小时")
p()

with open("results/jiaodafaxue-evaluation/batch-report.json") as f:
    batch = json.load(f)

p("## 批次报告")
p(f"| 指标 | 值 |")
p(f"|------|-----|")
p(f"| R1 完成 | {batch['r1_completed']}/{batch['total']} |")
p(f"| R2 完成 | {batch['r2_completed']}/{batch['total']} |")
p(f"| R1 平均分均值 | {batch['r1_avg_score_mean']:.2f} |")
p(f"| R1 平均最大 std | {batch['r1_avg_max_std']:.2f} |")
p(f"| R2 平均 std | {batch['r2_avg_std']:.2f} |")
p(f"| R2 收敛率 | {batch['r2_convergence_rate']} |")
p(f"| 内容审查问题 | {batch['content_inspection_issues']} |")
p()

# Score distribution
r2_avgs = [s['r2_avg'] for s in paper_stats]
p("## R2 最终得分分布")
p(f"- 论文数：{len(r2_avgs)}")
p(f"- 均值：{statistics.mean(r2_avgs):.2f}")
p(f"- 中位数：{statistics.median(r2_avgs):.2f}")
p(f"- 标准差：{statistics.stdev(r2_avgs):.2f}")
p(f"- 最小值：{min(r2_avgs):.2f}")
p(f"- 最大值：{max(r2_avgs):.2f}")
p()

bands = {'≥85 (优秀)': 0, '75-84 (良好)': 0, '65-74 (中等)': 0,
         '55-64 (及格)': 0, '45-54 (偏低)': 0, '<45 (不合格)': 0}
for s in r2_avgs:
    if s >= 85: bands['≥85 (优秀)'] += 1
    elif s >= 75: bands['75-84 (良好)'] += 1
    elif s >= 65: bands['65-74 (中等)'] += 1
    elif s >= 55: bands['55-64 (及格)'] += 1
    elif s >= 45: bands['45-54 (偏低)'] += 1
    else: bands['<45 (不合格)'] += 1

p("### 分数段分布")
p("| 分数段 | 论文数 | 占比 |")
p("|--------|--------|------|")
for band, count in bands.items():
    pct = count / len(r2_avgs) * 100
    p(f"| {band} | {count} | {pct:.1f}% |")
p()

# Dimension analysis
p("## 六维度分析（R1 → R2）")
p("| 维度 | R1 均值 | R2 均值 | 变化 | R1 avg_std | R2 avg_std | 降幅 |")
p("|------|---------|---------|------|-----------|-----------|------|")
for dk in dim_keys:
    r1_all, r2_all = dim_r1_scores[dk], dim_r2_scores[dk]
    r1_std_all, r2_std_all = dim_r1_stds[dk], dim_r2_stds[dk]
    r1_mean = statistics.mean(r1_all) if r1_all else 0
    r2_mean = statistics.mean(r2_all) if r2_all else 0
    r1_as = statistics.mean(r1_std_all) if r1_std_all else 0
    r2_as = statistics.mean(r2_std_all) if r2_std_all else 0
    diff = r2_mean - r1_mean
    red = (r1_as - r2_as) / r1_as * 100 if r1_as > 0 else 0
    p(f"| {dim_zh[dk]} | {r1_mean:.2f} | {r2_mean:.2f} | {diff:+.2f} | {r1_as:.2f} | {r2_as:.2f} | {red:.1f}% |")
p()

# Convergence
p("## 收敛分析")
p("| 阈值 | 论文数 | 占比 |")
p("|------|--------|------|")
for thresh in [5, 8, 12]:
    count = sum(1 for s in paper_stats if s['r2_avg_std'] <= thresh)
    pct = count / len(paper_stats) * 100
    p(f"| R2 avg_std ≤ {thresh} | {count} | {pct:.1f}% |")
p()

p("### 维度级收敛（R2 std ≤ 8）")
p("| 维度 | 收敛数 | 占比 |")
p("|------|--------|------|")
for dk in dim_keys:
    conv = sum(1 for s in dim_r2_stds[dk] if s <= 8)
    total = len(dim_r2_stds[dk])
    pct = conv / total * 100 if total > 0 else 0
    p(f"| {dim_zh[dk]} | {conv}/{total} | {pct:.1f}% |")
p()

# R1→R2 change
r1_avgs_list = [s['r1_avg'] for s in paper_stats]
changes = [s['r2_avg'] - s['r1_avg'] for s in paper_stats]
up = sum(1 for c in changes if c > 0)
down = sum(1 for c in changes if c < 0)
same = sum(1 for c in changes if c == 0)
p("## R1→R2 分数变化")
p(f"- 平均分：R1 {statistics.mean(r1_avgs_list):.2f} → R2 {statistics.mean(r2_avgs):.2f}（{statistics.mean(changes):+.2f}）")
p(f"- 上升：{up} 篇 | 下降：{down} 篇 | 不变：{same} 篇")
p(f"- 变化幅度：min={min(changes):+.2f}，max={max(changes):+.2f}，std={statistics.stdev(changes):.2f}")
p()

# Top 20
p("## Top 20 论文（R2 平均分）")
p("| 排名 | ID | R2 均分 | R2 avg_std | 论文 |")
p("|------|-----|---------|-----------|------|")
top20 = sorted(paper_stats, key=lambda x: x['r2_avg'], reverse=True)[:20]
for i, s in enumerate(top20, 1):
    fn = s['filename'].split('/')[-1].replace('.md', '')
    # Extract title part (after journal name)
    parts = fn.split('_', 4)
    title = parts[4] if len(parts) >= 5 else fn
    p(f"| {i} | {s['id']} | {s['r2_avg']:.1f} | {s['r2_avg_std']:.1f} | {title[:50]} |")
p()

# Bottom 10
p("## Bottom 10 论文（R2 平均分）")
p("| 排名 | ID | R2 均分 | R2 avg_std | 论文 |")
p("|------|-----|---------|-----------|------|")
bot10 = sorted(paper_stats, key=lambda x: x['r2_avg'])[:10]
for i, s in enumerate(bot10, 1):
    fn = s['filename'].split('/')[-1].replace('.md', '')
    parts = fn.split('_', 4)
    title = parts[4] if len(parts) >= 5 else fn
    p(f"| {i} | {s['id']} | {s['r2_avg']:.1f} | {s['r2_avg_std']:.1f} | {title[:50]} |")
p()

# High divergence
high_div = sorted([s for s in paper_stats if s['r2_avg_std'] > 12],
                  key=lambda x: x['r2_avg_std'], reverse=True)
p(f"## 高分歧论文（R2 avg_std > 12）：共 {len(high_div)} 篇")
if high_div:
    p("| ID | R2 均分 | avg_std | max_std | 论文 |")
    p("|-----|---------|---------|---------|------|")
    for s in high_div[:10]:
        fn = s['filename'].split('/')[-1].replace('.md', '')
        parts = fn.split('_', 4)
        title = parts[4] if len(parts) >= 5 else fn
        p(f"| {s['id']} | {s['r2_avg']:.1f} | {s['r2_avg_std']:.1f} | {s['r2_max_std']:.1f} | {title[:50]} |")
p()

# Year distribution
year_scores = defaultdict(list)
for s in paper_stats:
    fn = s['filename'].split('/')[-1]
    parts = fn.split('_')
    if len(parts) >= 3:
        try:
            year = int(parts[2])
            year_scores[year].append(s['r2_avg'])
        except (ValueError, IndexError):
            pass

if year_scores:
    p("## 年份分布")
    p("| 年份 | 论文数 | 均分 | 中位数 | std |")
    p("|------|--------|------|--------|-----|")
    for year in sorted(year_scores.keys()):
        scores = year_scores[year]
        avg = statistics.mean(scores)
        med = statistics.median(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        p(f"| {year} | {len(scores)} | {avg:.2f} | {med:.2f} | {std:.2f} |")
p()

# Model behavior
model_scores = defaultdict(list)
model_r1 = defaultdict(list)
model_r2 = defaultdict(list)
for pid, res in results.items():
    for dk in dim_keys:
        d = res.get('dimensions', {}).get(dk, {})
        r1 = d.get('round1_scores', {})
        r2 = d.get('round2_scores', {})
        for model, score in r2.items():
            if isinstance(score, (int, float)):
                model_scores[model].append(score)
        for model in r1:
            if model in r2 and isinstance(r1[model], (int, float)) and isinstance(r2[model], (int, float)):
                model_r1[model].append(r1[model])
                model_r2[model].append(r2[model])

p("## 模型行为分析")
p("### R2 最终评分分布")
p("| 模型 | 评分数 | 均值 | 中位数 | std |")
p("|------|--------|------|--------|-----|")
for model in sorted(model_scores.keys()):
    scores = model_scores[model]
    p(f"| {model} | {len(scores)} | {statistics.mean(scores):.2f} | {statistics.median(scores):.2f} | {statistics.stdev(scores):.2f} |")
p()

p("### R1→R2 模型变化")
p("| 模型 | R1 均值 | R2 均值 | 变化 | 变化维度占比 |")
p("|------|---------|---------|------|------------|")
for model in sorted(model_r1.keys()):
    r1_avg = statistics.mean(model_r1[model])
    r2_avg = statistics.mean(model_r2[model])
    diff = r2_avg - r1_avg
    ch = [r2 - r1 for r1, r2 in zip(model_r1[model], model_r2[model])]
    changed = sum(1 for c in ch if c != 0)
    pct = changed / len(ch) * 100 if ch else 0
    p(f"| {model} | {r1_avg:.2f} | {r2_avg:.2f} | {diff:+.2f} | {pct:.1f}% |")
p()

# Std improvement
std_imps = []
for s in paper_stats:
    if s['r1_avg_std'] > 0:
        std_imps.append((s['r1_avg_std'] - s['r2_avg_std']) / s['r1_avg_std'] * 100)

if std_imps:
    p("## R1→R2 std 降幅分布")
    p(f"- 平均降幅：{statistics.mean(std_imps):.1f}%")
    p(f"- 中位数降幅：{statistics.median(std_imps):.1f}%")
    p()
    bands2 = {'>50%': 0, '30-50%': 0, '10-30%': 0, '0-10%': 0, '<0% (恶化)': 0}
    for s in std_imps:
        if s > 50: bands2['>50%'] += 1
        elif s > 30: bands2['30-50%'] += 1
        elif s > 10: bands2['10-30%'] += 1
        elif s > 0: bands2['0-10%'] += 1
        else: bands2['<0% (恶化)'] += 1
    p("| 降幅区间 | 论文数 | 占比 |")
    p("|----------|--------|------|")
    for band, count in bands2.items():
        pct = count / len(std_imps) * 100
        p(f"| {band} | {count} | {pct:.1f}% |")

# Write output
output = "\n".join(out)
print(output)

# Also save to file
with open("results/jiaodafaxue-evaluation/summary-report.md", "w", encoding="utf-8") as f:
    f.write(output)
print("\n\n[Report saved to results/jiaodafaxue-evaluation/summary-report.md]")
