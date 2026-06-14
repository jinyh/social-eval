#!/usr/bin/env python3
"""交大法学期刊：五轴位置归属度 + 六维质量评价 综合分析"""

import json
import csv
import re
import math
from pathlib import Path
from collections import defaultdict, Counter

# === 路径 ===
EVAL_DIR = Path("results/jiaodafaxue-evaluation/round2")
POS_DIR = Path("results/jiaodafaxue-position-assessment/merged")
PAPER_LIST = Path("results/jiaodafaxue-paper-list.json")
SUMMARY_JSON = Path("results/jiaodafaxue-position-assessment/merged/summary.json")

# === 维度/轴名称映射 ===
DIM_ZH = {
    "problem_originality": "研究创新性",
    "literature_insight": "现状洞察度",
    "analytical_framework": "理论建构力",
    "logical_coherence": "逻辑连贯性",
    "conclusion_consensus": "学术共识度",
    "forward_extension": "前瞻延展性",
}
AXIS_ZH = {
    "object_belonging": "对象归属度",
    "material_belonging": "材料归属度",
    "category_autonomy": "范畴自主度",
    "explanatory_orientation": "解释目标归属度",
    "system_mappability": "体系映射度",
}
ROUTE_ZH = {
    "chinese_doctrinal": "中国教义",
    "comparative_localization": "比较法本土化",
    "china_practice_governance": "中国实践治理",
    "chinese_legal_theory": "中国法理论",
    "traditional_resource_transform": "传统资源转化",
    "weakly_related": "弱关联",
    "interdisciplinary_china_data": "跨学科中国数据",
}
STRENGTH_ZH = {"strong": "强", "medium": "中", "weak": "弱", "absent": "无"}

# === 工具函数 ===
def mean(xs):
    return sum(xs) / len(xs) if xs else 0

def std(xs):
    if len(xs) < 2:
        return 0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

def percentile(xs, p):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0
    k = (n - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < n else f
    return s[f] + (k - f) * (s[c] - s[f])

def corr(xs, ys):
    """Pearson 相关系数"""
    n = len(xs)
    if n < 3:
        return 0
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return 0
    return sxy / math.sqrt(sxx * syy)

def fmt(x, d=2):
    return f"{x:.{d}f}"

# === 加载数据 ===
print("加载数据...")

# 论文列表（提取年份）
with open(PAPER_LIST) as f:
    paper_meta = {p["id"]: p for p in json.load(f)["papers"]}

# 解析年份
def extract_year(filename):
    m = re.search(r"_(\d{4})_", filename)
    return int(m.group(1)) if m else None

for pid, p in paper_meta.items():
    p["year"] = extract_year(p.get("filename", ""))

# 六维评价结果（642 篇）
eval_data = {}
for fp in EVAL_DIR.glob("paper-*.json"):
    pid = int(fp.stem.replace("paper-", ""))
    with open(fp) as f:
        d = json.load(f)
    dims = {}
    for dim_key, dim_val in d["dimensions"].items():
        dims[dim_key] = {
            "r2_mean": dim_val.get("round2_mean"),
            "r2_std": dim_val.get("round2_std"),
            "r1_mean": dim_val.get("round1_mean"),
        }
    overall = d.get("overall", {})
    eval_data[pid] = {
        "dims": dims,
        "final_score_r2": overall.get("round2_final_score_mean"),
        "final_score_r1": overall.get("round1_final_score_mean"),
        "r1_avg_std": overall.get("round1_avg_std"),
        "r2_avg_std": overall.get("round2_avg_std"),
    }

# 五轴位置归属度结果（311 篇）
pos_data = {}
for fp in POS_DIR.glob("paper-*.json"):
    pid = int(fp.stem.replace("paper-", ""))
    with open(fp) as f:
        d = json.load(f)
    final = d.get("final", {})
    axes = {}
    for ax_key, ax_val in final.get("axis_scores", {}).items():
        axes[ax_key] = ax_val.get("score", 0)
    pos_data[pid] = {
        "axes": axes,
        "total_score": final.get("total_score", 0),
        "strength": final.get("strength", ""),
        "route": final.get("research_route", {}).get("primary", ""),
        "agreement_level": final.get("agreement_level", ""),
        "disputed_axes": final.get("disputed_axes", []),
        "review_required": final.get("review_required", False),
    }

print(f"  六维评价：{len(eval_data)} 篇")
print(f"  五轴评估：{len(pos_data)} 篇")
print(f"  两者交集：{len(set(eval_data) & set(pos_data))} 篇")
print()

# =====================================================
# 第一部分：六维评价全量分析（642 篇）
# =====================================================
print("=" * 70)
print("第一部分：六维质量评价统计（642 篇）")
print("=" * 70)

# 1.1 各维度分布
print("\n### 1.1 各维度 Round 2 评分分布\n")
print(f"{'维度':<12} {'均值':>6} {'中位':>6} {'std':>6} {'P25':>6} {'P75':>6} {'Min':>6} {'Max':>6}")
print("-" * 62)

all_final_scores = []
dim_scores = {}
for dim_key in DIM_ZH:
    scores = [
        eval_data[pid]["dims"][dim_key]["r2_mean"]
        for pid in eval_data
        if eval_data[pid]["dims"][dim_key]["r2_mean"] is not None
    ]
    dim_scores[dim_key] = scores
    print(
        f"{DIM_ZH[dim_key]:<10} {fmt(mean(scores)):>6} {fmt(median(scores)):>6} "
        f"{fmt(std(scores)):>6} {fmt(percentile(scores, 25)):>6} {fmt(percentile(scores, 75)):>6} "
        f"{fmt(min(scores)):>6} {fmt(max(scores)):>6}"
    )

# 1.2 总分分布
print("\n### 1.2 加权总分（final_score）分布\n")
final_scores = [
    eval_data[pid]["final_score_r2"]
    for pid in eval_data
    if eval_data[pid]["final_score_r2"] is not None
]
print(f"  N = {len(final_scores)}")
print(f"  均值 = {fmt(mean(final_scores))}")
print(f"  中位数 = {fmt(median(final_scores))}")
print(f"  标准差 = {fmt(std(final_scores))}")
print(f"  P25 = {fmt(percentile(final_scores, 25))}")
print(f"  P75 = {fmt(percentile(final_scores, 75))}")
print(f"  范围 = [{fmt(min(final_scores))}, {fmt(max(final_scores))}]")

# 分档
bins = [(0, 30, "极差"), (30, 45, "差"), (45, 55, "及格线以下"),
        (55, 65, "中等"), (65, 75, "良好"), (75, 100, "优秀")]
print(f"\n  分档统计：")
for lo, hi, label in bins:
    cnt = sum(1 for s in final_scores if lo <= s < hi)
    print(f"    {label} ({lo}-{hi}): {cnt} ({fmt(cnt/len(final_scores)*100, 1)}%)")

# 1.3 收敛情况
print("\n### 1.3 Round 1 → Round 2 收敛效果\n")
r1_stds = [eval_data[pid]["r1_avg_std"] for pid in eval_data if eval_data[pid]["r1_avg_std"] is not None]
r2_stds = [eval_data[pid]["r2_avg_std"] for pid in eval_data if eval_data[pid]["r2_avg_std"] is not None]
print(f"  R1 平均 std：{fmt(mean(r1_stds))}")
print(f"  R2 平均 std：{fmt(mean(r2_stds))}")
print(f"  收敛幅度：{fmt(mean(r1_stds) - mean(r2_stds))} ({fmt((mean(r1_stds) - mean(r2_stds))/mean(r1_stds)*100, 1)}%)")

# 1.4 年度趋势
print("\n### 1.4 年度趋势\n")
year_scores = defaultdict(list)
for pid in eval_data:
    if eval_data[pid]["final_score_r2"] is not None:
        y = paper_meta.get(pid, {}).get("year")
        if y:
            year_scores[y].append(eval_data[pid]["final_score_r2"])

print(f"{'年份':>6} {'N':>5} {'均值':>7} {'中位':>7} {'std':>7}")
print("-" * 36)
for y in sorted(year_scores):
    s = year_scores[y]
    print(f"{y:>6} {len(s):>5} {fmt(mean(s)):>7} {fmt(median(s)):>7} {fmt(std(s)):>7}")

# =====================================================
# 第二部分：五轴位置归属度分析（311 篇）
# =====================================================
print("\n" + "=" * 70)
print("第二部分：五轴位置归属度统计（311 篇，final_score > 55）")
print("=" * 70)

# 2.1 各轴分布
print("\n### 2.1 各轴评分分布（0-2）\n")
print(f"{'轴':<14} {'均值':>6} {'0分':>6} {'1分':>6} {'2分':>6}")
print("-" * 42)

axis_scores = {}
for ax_key in AXIS_ZH:
    scores = [pos_data[pid]["axes"].get(ax_key, 0) for pid in pos_data]
    axis_scores[ax_key] = scores
    c = Counter(scores)
    print(
        f"{AXIS_ZH[ax_key]:<12} {fmt(mean(scores)):>6} "
        f"{c.get(0,0):>6} {c.get(1,0):>6} {c.get(2,0):>6}"
    )

# 2.2 总分分布
print("\n### 2.2 五轴总分分布（0-10）\n")
total_scores = [pos_data[pid]["total_score"] for pid in pos_data]
c = Counter(total_scores)
print(f"{'分数':>6} {'篇数':>6} {'占比':>8} {'累计':>8}")
print("-" * 32)
cum = 0
for s in range(11):
    cnt = c.get(s, 0)
    cum += cnt
    bar = "█" * (cnt // 3)
    print(f"{s:>6} {cnt:>6} {fmt(cnt/len(total_scores)*100, 1):>7}% {fmt(cum/len(total_scores)*100, 1):>7}% {bar}")

print(f"\n  均值 = {fmt(mean(total_scores))}")
print(f"  中位数 = {fmt(median(total_scores))}")
print(f"  标准差 = {fmt(std(total_scores))}")

# 2.3 强度分档
print("\n### 2.3 强度分档\n")
strength_counts = Counter(pos_data[pid]["strength"] for pid in pos_data)
for s in ["strong", "medium", "weak", "absent"]:
    cnt = strength_counts.get(s, 0)
    print(f"  {STRENGTH_ZH[s]} ({s}): {cnt} ({fmt(cnt/len(pos_data)*100, 1)}%)")

# 2.4 研究路径分布
print("\n### 2.4 研究路径分布\n")
route_counts = Counter(pos_data[pid]["route"] for pid in pos_data)
for r, cnt in route_counts.most_common():
    zh = ROUTE_ZH.get(r, r)
    print(f"  {zh} ({r}): {cnt} ({fmt(cnt/len(pos_data)*100, 1)}%)")

# 2.5 各轴满分率与零分率
print("\n### 2.5 各轴满分率与零分率\n")
print(f"{'轴':<14} {'满分率(=2)':>10} {'零分率(=0)':>10}")
print("-" * 38)
for ax_key in AXIS_ZH:
    scores = axis_scores[ax_key]
    full = sum(1 for s in scores if s == 2)
    zero = sum(1 for s in scores if s == 0)
    print(f"{AXIS_ZH[ax_key]:<12} {fmt(full/len(scores)*100, 1):>9}% {fmt(zero/len(scores)*100, 1):>9}%")

# =====================================================
# 第三部分：六维 × 五轴 交叉分析
# =====================================================
print("\n" + "=" * 70)
print("第三部分：六维质量 × 五轴位置 交叉分析")
print("=" * 70)

# 构建联合数据集
joint = {}
for pid in pos_data:
    if pid in eval_data and eval_data[pid]["final_score_r2"] is not None:
        joint[pid] = {
            "final_score": eval_data[pid]["final_score_r2"],
            "pos_total": pos_data[pid]["total_score"],
            "strength": pos_data[pid]["strength"],
            "route": pos_data[pid]["route"],
            "dims": {dk: eval_data[pid]["dims"][dk]["r2_mean"] for dk in DIM_ZH if eval_data[pid]["dims"][dk]["r2_mean"] is not None},
            "axes": pos_data[pid]["axes"],
        }

print(f"\n  联合数据集：{len(joint)} 篇")

# 3.1 总分相关性
print("\n### 3.1 六维总分 vs 五轴总分 相关性\n")
fs = [joint[pid]["final_score"] for pid in joint]
ps = [joint[pid]["pos_total"] for pid in joint]
r = corr(fs, ps)
print(f"  Pearson r = {fmt(r, 3)}")
print(f"  （六维 final_score 与五轴 total_score 的线性相关程度）")

# 3.2 各维度 vs 各轴相关矩阵
print("\n### 3.2 六维 × 五轴 相关矩阵（Pearson r）\n")
header = f"{'':>14}" + "".join(f"{AXIS_ZH[ax]:>12}" for ax in AXIS_ZH) + f"{'五轴总分':>10}"
print(header)
print("-" * len(header))

for dk in DIM_ZH:
    dim_vals = [joint[pid]["dims"].get(dk, 0) for pid in joint]
    row = f"{DIM_ZH[dk]:<12}"
    for ax in AXIS_ZH:
        ax_vals = [joint[pid]["axes"].get(ax, 0) for pid in joint]
        row += f"{fmt(corr(dim_vals, ax_vals), 3):>12}"
    row += f"{fmt(corr(dim_vals, ps), 3):>10}"
    print(row)

# 五轴总分 vs 各维度
row = f"{'六维总分':<12}"
for ax in AXIS_ZH:
    ax_vals = [joint[pid]["axes"].get(ax, 0) for pid in joint]
    row += f"{fmt(corr(fs, ax_vals), 3):>12}"
row += f"{fmt(r, 3):>10}"
print(row)

# 3.3 按强度分档的六维分数对比
print("\n### 3.3 按五轴强度分档的六维均分对比\n")
strength_final = defaultdict(list)
for pid in joint:
    strength_final[joint[pid]["strength"]].append(joint[pid]["final_score"])

print(f"{'强度':>8} {'N':>5} {'六维均分':>8} {'六维中位':>8} {'六维std':>8}")
print("-" * 42)
for s in ["strong", "medium", "weak", "absent"]:
    vals = strength_final.get(s, [])
    if vals:
        print(f"{STRENGTH_ZH[s]:>6} {len(vals):>5} {fmt(mean(vals)):>8} {fmt(median(vals)):>8} {fmt(std(vals)):>8}")

# 3.4 按研究路径的六维分数对比
print("\n### 3.4 按研究路径的六维均分与五轴均分\n")
route_final = defaultdict(list)
route_pos = defaultdict(list)
for pid in joint:
    route_final[joint[pid]["route"]].append(joint[pid]["final_score"])
    route_pos[joint[pid]["route"]].append(joint[pid]["pos_total"])

print(f"{'路径':<18} {'N':>5} {'六维均分':>8} {'五轴均分':>8}")
print("-" * 44)
for r_key in sorted(route_final, key=lambda x: -len(route_final[x])):
    zh = ROUTE_ZH.get(r_key, r_key)
    print(f"{zh:<16} {len(route_final[r_key]):>5} {fmt(mean(route_final[r_key])):>8} {fmt(mean(route_pos[r_key])):>8}")

# 3.5 高分论文特征（六维 Top 10% + 五轴 strong）
print("\n### 3.5 高质量 + 强归属 论文特征\n")
p90 = percentile(fs, 90)
high_both = [pid for pid in joint if joint[pid]["final_score"] >= p90 and joint[pid]["strength"] == "strong"]
high_score_only = [pid for pid in joint if joint[pid]["final_score"] >= p90 and joint[pid]["strength"] != "strong"]
low_score_high_pos = [pid for pid in joint if joint[pid]["final_score"] < p90 and joint[pid]["strength"] == "strong"]

print(f"  六维 P90 阈值 = {fmt(p90)}")
print(f"  双高（六维 Top10% + 五轴 strong）：{len(high_both)} 篇")
print(f"  仅六维高（Top10% 但非 strong）：{len(high_score_only)} 篇")
print(f"  仅五轴强（strong 但六维 < P90）：{len(low_score_high_pos)} 篇")

# 双高论文的研究路径分布
if high_both:
    print(f"\n  双高论文研究路径：")
    hb_routes = Counter(joint[pid]["route"] for pid in high_both)
    for r_key, cnt in hb_routes.most_common():
        zh = ROUTE_ZH.get(r_key, r_key)
        print(f"    {zh}: {cnt} ({fmt(cnt/len(high_both)*100, 1)}%)")

# 3.6 五轴各轴 vs 六维各维度的均分关系
print("\n### 3.6 五轴得分=0 vs =2 时的六维均分对比\n")
print(f"{'轴':<12} {'六维维度':<12} {'轴=0均分':>10} {'轴=2均分':>10} {'差值':>8}")
print("-" * 56)
for ax_key in AXIS_ZH:
    for dk in DIM_ZH:
        ax0 = [joint[pid]["dims"].get(dk, 0) for pid in joint if joint[pid]["axes"].get(ax_key, 0) == 0]
        ax2 = [joint[pid]["dims"].get(dk, 0) for pid in joint if joint[pid]["axes"].get(ax_key, 0) == 2]
        if ax0 and ax2:
            diff = mean(ax2) - mean(ax0)
            if abs(diff) > 3:  # 只显示差异较大的
                print(f"{AXIS_ZH[ax_key]:<10} {DIM_ZH[dk]:<10} {fmt(mean(ax0)):>10} {fmt(mean(ax2)):>10} {fmt(diff, 1):>8}")

# 3.7 年度 × 五轴趋势
print("\n### 3.7 年度趋势：六维 + 五轴\n")
year_pos = defaultdict(list)
year_eval_all = defaultdict(list)  # 全量 642
for pid in joint:
    y = paper_meta.get(pid, {}).get("year")
    if y:
        year_pos[y].append(joint[pid]["pos_total"])

for pid in eval_data:
    if eval_data[pid]["final_score_r2"] is not None:
        y = paper_meta.get(pid, {}).get("year")
        if y:
            year_eval_all[y].append(eval_data[pid]["final_score_r2"])

print(f"{'年份':>6} {'六维N':>6} {'六维均分':>8} {'五轴N':>6} {'五轴均分':>8} {'五轴strong%':>10}")
print("-" * 52)
for y in sorted(year_eval_all):
    e_vals = year_eval_all[y]
    p_vals = year_pos.get(y, [])
    p_strong = sum(1 for pid in joint if paper_meta.get(pid, {}).get("year") == y and joint[pid]["strength"] == "strong")
    p_total_y = len(p_vals)
    strong_pct = fmt(p_strong / p_total_y * 100, 1) if p_total_y > 0 else "-"
    p_mean = fmt(mean(p_vals)) if p_vals else "-"
    print(f"{y:>6} {len(e_vals):>6} {fmt(mean(e_vals)):>8} {len(p_vals):>6} {p_mean:>8} {strong_pct:>9}%")

# =====================================================
# 第四部分：关键发现总结
# =====================================================
print("\n" + "=" * 70)
print("第四部分：关键发现")
print("=" * 70)

# 发现 1：总体质量
below_55 = sum(1 for s in final_scores if s < 55)
print(f"\n  1. 六维质量分布：{below_55}/{len(final_scores)} ({fmt(below_55/len(final_scores)*100, 1)}%) 篇低于 55 分")

# 发现 2：五轴总分高度右偏
perfect = sum(1 for s in total_scores if s == 10)
print(f"  2. 五轴总分严重右偏：{perfect}/{len(total_scores)} ({fmt(perfect/len(total_scores)*100, 1)}%) 篇满分 10/10")

# 发现 3：相关性
print(f"  3. 六维 ↔ 五轴相关性：r = {fmt(r, 3)}（{'弱' if abs(r) < 0.3 else '中等' if abs(r) < 0.5 else '强'}相关）")

# 发现 4：各轴区分度
axis_stds = {AXIS_ZH[k]: std(axis_scores[k]) for k in AXIS_ZH}
most_var = max(axis_stds, key=axis_stds.get)
least_var = min(axis_stds, key=axis_stds.get)
print(f"  4. 区分度最高轴：{most_var} (std={fmt(axis_stds[most_var])})")
print(f"     区分度最低轴：{least_var} (std={fmt(axis_stds[least_var])})")

# 发现 5：研究路径集中度
top3_routes = route_counts.most_common(3)
top3_pct = sum(c for _, c in top3_routes) / len(pos_data) * 100
print(f"  5. 前三路径集中度：{fmt(top3_pct, 1)}%（{', '.join(ROUTE_ZH.get(r, r) for r, _ in top3_routes)}）")

# 发现 6：双高论文
print(f"  6. 双高论文（六维 Top10% + 五轴 strong）：{len(high_both)} 篇（占交集 {fmt(len(high_both)/len(joint)*100, 1)}%）")

# 发现 7：R2 收敛
print(f"  7. R2 收敛效果：avg std {fmt(mean(r1_stds))} → {fmt(mean(r2_stds))}（↓{fmt(mean(r1_stds) - mean(r2_stds))}）")

print("\n分析完成。")
