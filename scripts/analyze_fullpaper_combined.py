#!/usr/bin/env python3
"""1920 篇三大刊：五轴 × 六维综合分析 + Top 50 选出策略"""

import csv
import re
import math
from collections import defaultdict, Counter

# === 工具 ===
def mean(xs): return sum(xs)/len(xs) if xs else 0
def std(xs):
    if len(xs) < 2: return 0
    m = mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))
def median(xs):
    s = sorted(xs); n = len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
def percentile(xs, p):
    s = sorted(xs); n = len(s); k = (n-1)*p/100; f = int(k); c = min(f+1, n-1)
    return s[f] + (k-f)*(s[c]-s[f])
def corr(xs, ys):
    n = len(xs)
    if n < 3: return 0
    mx, my = mean(xs), mean(ys)
    sxx = sum((x-mx)**2 for x in xs); syy = sum((y-my)**2 for y in ys)
    sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    return sxy/math.sqrt(sxx*syy) if sxx and syy else 0
def fmt(x, d=2): return f"{x:.{d}f}"

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

# === 加载 ===
print("加载数据...")

# 元数据（学科）
meta = {}
with open("results/merged-metadata.csv", "r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        meta[int(row["编号"])] = row

# report.md 表格
data = {}
with open("results/fullpaper-position-assessment-stage0/report.md") as f:
    in_table = False
    for line in f:
        line = line.strip()
        if line.startswith("| PID |"):
            in_table = True; continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 11:
                pid = int(cols[0])
                six_score = float(cols[3]) if cols[3] else None
                pos_score = int(cols[4]) if cols[4] else 0
                data[pid] = {
                    "year": int(cols[1]) if cols[1] else 0,
                    "journal": cols[2],
                    "final_score": six_score,
                    "pos_total": pos_score,
                    "strength": cols[5],
                    "route": cols[6],
                    "r2_mode": cols[7],
                    "precheck": cols[8],
                    "review": cols[9] == "是",
                    "title": cols[10],
                    "discipline": meta.get(pid, {}).get("分类", ""),
                    "author": meta.get(pid, {}).get("作者", ""),
                }

valid = {pid: d for pid, d in data.items() if d["final_score"] is not None}
print(f"  元数据：{len(meta)} 篇")
print(f"  report 解析：{len(data)} 篇")
print(f"  有效（有六维分）：{len(valid)} 篇\n")

# =====================================================
# 第一部分：全景统计
# =====================================================
print("=" * 72)
print("第一部分：1920 篇全景统计")
print("=" * 72)

scores = [d["final_score"] for d in valid.values()]
pos_scores = [d["pos_total"] for d in valid.values()]

print(f"\n### 1.1 六维加权总分\n")
print(f"  N={len(scores)}  均值={fmt(mean(scores))}  中位={fmt(median(scores))}  std={fmt(std(scores))}")
print(f"  P10={fmt(percentile(scores,10))}  P25={fmt(percentile(scores,25))}  P50={fmt(median(scores))}  P75={fmt(percentile(scores,75))}  P90={fmt(percentile(scores,90))}")
print(f"  范围=[{fmt(min(scores))}, {fmt(max(scores))}]")

print(f"\n  分档：")
for lo,hi,label in [(0,30,"极差"),(30,45,"差"),(45,55,"中下"),(55,65,"中等"),(65,75,"良好"),(75,85,"优秀"),(85,100,"卓越")]:
    cnt = sum(1 for s in scores if lo <= s < hi)
    print(f"    {label}({lo:>2}-{hi}): {cnt:>4} ({fmt(cnt/len(scores)*100,1):>5}%)")

print(f"\n### 1.2 五轴总分\n")
c = Counter(pos_scores)
print(f"{'分':>3} {'篇数':>6} {'占比':>7} {'累计':>7}  柱状")
cum = 0
for s in range(11):
    cnt = c.get(s, 0); cum += cnt
    bar = "█" * (cnt // 10)
    print(f"{s:>3} {cnt:>6} {fmt(cnt/len(pos_scores)*100,1):>6}% {fmt(cum/len(pos_scores)*100,1):>6}%  {bar}")
print(f"\n  均值={fmt(mean(pos_scores))}  中位={fmt(median(pos_scores))}  std={fmt(std(pos_scores))}")

print(f"\n### 1.3 五轴强度\n")
sc = Counter(d["strength"] for d in valid.values())
for s in ["strong","medium","weak","absent"]:
    cnt = sc.get(s,0)
    print(f"  {STRENGTH_ZH[s]:>2}({s:>6}): {cnt:>4} ({fmt(cnt/len(valid)*100,1)}%)")

print(f"\n### 1.4 研究路径\n")
rc = Counter(d["route"] for d in valid.values())
for r, cnt in rc.most_common():
    print(f"  {ROUTE_ZH.get(r,r):<14} {cnt:>4} ({fmt(cnt/len(valid)*100,1)}%)")

print(f"\n### 1.5 各轴区分度（基于 summary.json 统计）\n")
# 从 summary.json 获取轴级数据
import json as _json
with open("results/fullpaper-position-assessment-stage0/summary.json") as _f:
    _summary = _json.load(_f)
print(f"  （各轴逐篇数据需读取 1920 个 JSON，此处仅展示总体分布）")
print(f"  五轴总分分布：")
for score_str in sorted(_summary["score_distribution"], key=lambda x: int(x)):
    cnt = _summary["score_distribution"][score_str]
    print(f"    {score_str} 分: {cnt} 篇")

# =====================================================
# 第二部分：学科维度
# =====================================================
print(f"\n{'='*72}")
print("第二部分：学科维度分析")
print("=" * 72)

disc_data = defaultdict(lambda: {"scores":[], "pos":[], "strong":0, "n":0})
for pid, d in valid.items():
    dd = disc_data[d["discipline"]]
    dd["scores"].append(d["final_score"])
    dd["pos"].append(d["pos_total"])
    dd["n"] += 1
    if d["strength"] == "strong": dd["strong"] += 1

print(f"\n### 2.1 各学科统计\n")
print(f"{'学科':<16} {'N':>5} {'六维均':>7} {'六维中位':>8} {'五轴均':>7} {'强%':>6} {'≥75分':>5}")
print("-" * 62)
for disc in sorted(disc_data, key=lambda x: -disc_data[x]["n"]):
    dd = disc_data[disc]
    s, p = dd["scores"], dd["pos"]
    print(f"{disc:<14} {len(s):>5} {fmt(mean(s)):>7} {fmt(median(s)):>8} {fmt(mean(p)):>7} {fmt(dd['strong']/dd['n']*100,1):>5}% {sum(1 for x in s if x>=75):>5}")

# 学科 × 期刊
print(f"\n### 2.2 学科 × 期刊\n")
dj = defaultdict(Counter)
for d in valid.values(): dj[d["discipline"]][d["journal"]] += 1
print(f"{'学科':<16} {'中国法学':>8} {'法学研究':>8} {'社科':>6}")
print("-" * 42)
for disc in sorted(dj, key=lambda x: -sum(dj[x].values())):
    print(f"{disc:<14} {dj[disc].get('中国法学',0):>8} {dj[disc].get('法学研究',0):>8} {dj[disc].get('中国社会科学',0):>6}")

# =====================================================
# 第三部分：交叉分析
# =====================================================
print(f"\n{'='*72}")
print("第三部分：六维 × 五轴 交叉分析")
print("=" * 72)

fs = [d["final_score"] for d in valid.values()]
ps = [d["pos_total"] for d in valid.values()]
r = corr(fs, ps)

print(f"\n### 3.1 相关性\n")
print(f"  六维总分 vs 五轴总分：r = {fmt(r, 3)}（弱相关）")
print(f"  → 两个维度测量不同属性，五轴提供独立于质量的归属度信息")

print(f"\n### 3.2 按五轴强度看六维\n")
print(f"{'强度':>4} {'N':>5} {'六维均':>7} {'中位':>7} {'P25':>7} {'P75':>7}")
print("-" * 42)
for s in ["strong","medium","weak","absent"]:
    vals = [d["final_score"] for d in valid.values() if d["strength"]==s]
    if vals:
        print(f"{STRENGTH_ZH[s]:>4} {len(vals):>5} {fmt(mean(vals)):>7} {fmt(median(vals)):>7} {fmt(percentile(vals,25)):>7} {fmt(percentile(vals,75)):>7}")

print(f"\n### 3.3 按五轴分档看六维\n")
for lo,hi,label in [(0,4,"低(0-3)"),(4,7,"中低(4-6)"),(7,9,"中高(7-8)"),(9,11,"高(9-10)")]:
    vals = [d["final_score"] for d in valid.values() if lo <= d["pos_total"] < hi]
    if vals:
        print(f"  {label}: N={len(vals):>4}  六维均={fmt(mean(vals))}  ≥75分={sum(1 for v in vals if v>=75)}")

print(f"\n### 3.4 研究路径 × 六维\n")
rs = defaultdict(list)
for d in valid.values(): rs[d["route"]].append(d["final_score"])
print(f"{'路径':<14} {'N':>5} {'六维均':>7} {'中位':>7} {'≥75':>5}")
print("-" * 42)
for r in sorted(rs, key=lambda x: -mean(rs[x])):
    vals = rs[r]
    print(f"{ROUTE_ZH.get(r,r):<12} {len(vals):>5} {fmt(mean(vals)):>7} {fmt(median(vals)):>7} {sum(1 for v in vals if v>=75):>5}")

# 五轴满分 vs 非满分
full10 = [d["final_score"] for d in valid.values() if d["pos_total"] == 10]
not10 = [d["final_score"] for d in valid.values() if d["pos_total"] < 10]
print(f"\n### 3.5 五轴满分 vs 非满分\n")
print(f"  满分(N={len(full10)}): 均={fmt(mean(full10))}  中位={fmt(median(full10))}  P90={fmt(percentile(full10,90))}")
print(f"  非满分(N={len(not10)}): 均={fmt(mean(not10))}  中位={fmt(median(not10))}  P90={fmt(percentile(not10,90))}")

# =====================================================
# 第四部分：Top 50 选出策略
# =====================================================
print(f"\n{'='*72}")
print("第四部分：Top 50 选出策略")
print("=" * 72)

# 学科配额
total_n = sum(dd["n"] for dd in disc_data.values())
MIN_FLOOR = 2
raw_q = {d: dd["n"]/total_n*50 for d, dd in disc_data.items()}
quotas = {d: max(MIN_FLOOR, round(q)) for d, q in raw_q.items()}
# 调整总和
diff = sum(quotas.values()) - 50
if diff > 0:
    for d in sorted(quotas, key=lambda x: -quotas[x]):
        if diff <= 0: break
        red = min(quotas[d] - MIN_FLOOR, diff)
        quotas[d] -= red; diff -= red
elif diff < 0:
    for d in sorted(raw_q, key=lambda x: raw_q[x] - int(raw_q[x]), reverse=True):
        if diff >= 0: break
        quotas[d] += 1; diff += 1

print(f"\n### 4.1 学科配额（保底={MIN_FLOOR}）\n")
print(f"{'学科':<16} {'1920数':>6} {'占比':>7} {'纯比例':>7} {'配额':>5}")
print("-" * 45)
for d in sorted(quotas, key=lambda x: -quotas[x]):
    print(f"{d:<14} {disc_data[d]['n']:>6} {fmt(disc_data[d]['n']/total_n*100,1):>6}% {fmt(raw_q[d],1):>7} {quotas[d]:>5}")
print(f"{'合计':<14} {total_n:>6} {'100.0%':>7} {'50.0':>7} {sum(quotas.values()):>5}")

# 四种策略
def select_by_strategy(valid, quotas, pos_filter=None, score_key="final_score"):
    by_disc = defaultdict(list)
    for pid, d in valid.items():
        if pos_filter and not pos_filter(d): continue
        by_disc[d["discipline"]].append((pid, d[score_key], d))
    sel = []
    for disc, q in quotas.items():
        cands = sorted(by_disc.get(disc,[]), key=lambda x: -x[1])[:q]
        sel.extend([(pid, s, disc, d) for pid, s, d in cands])
    return sel

def composite(d): return d["final_score"] * 0.8 + d["pos_total"] * 2 * 0.2

strategies = {}
# A: 纯六维
sel_a = select_by_strategy(valid, quotas)
strategies["A:纯六维+配额"] = sel_a
# B: 五轴≥8 过滤
sel_b = select_by_strategy(valid, quotas, pos_filter=lambda d: d["pos_total"] >= 8)
strategies["B:五轴≥8+六维+配额"] = sel_b
# C: 复合分
valid_c = {pid: {**d, "_comp": composite(d)} for pid, d in valid.items()}
sel_c = select_by_strategy(valid_c, quotas, score_key="_comp")
strategies["C:复合分(0.8+0.2)+配额"] = sel_c
# D: 五轴分层（10→8-9→≤7）
def select_tiered(valid, quotas):
    tiers = [[],[],[]]
    for pid, d in valid.items():
        if d["pos_total"] == 10: tiers[0].append((pid,d))
        elif d["pos_total"] >= 8: tiers[1].append((pid,d))
        else: tiers[2].append((pid,d))
    sel = []
    for disc, q in quotas.items():
        rem = q
        for tier in tiers:
            cands = [(pid, d["final_score"], d) for pid, d in tier if d["discipline"]==disc]
            cands.sort(key=lambda x: -x[1])
            take = cands[:rem]
            sel.extend([(pid,s,disc,d) for pid,s,d in take])
            rem -= len(take)
            if rem <= 0: break
    return sel
sel_d = select_tiered(valid, quotas)
strategies["D:五轴分层+六维+配额"] = sel_d

print(f"\n### 4.2 四策略对比\n")
for name, sel in strategies.items():
    sel_scores = [s for _,s,_,_ in sel]
    pids = set(pid for pid,_,_,_ in sel)
    strengths = Counter(valid[pid]["strength"] for pid in pids)
    journals = Counter(valid[pid]["journal"] for pid in pids)
    discs = Counter(disc for _,_,disc,_ in sel)
    pos_vals = [valid[pid]["pos_total"] for pid in pids]
    print(f"  【{name}】")
    print(f"    N={len(sel)}  六维：均={fmt(mean(sel_scores))} 中位={fmt(median(sel_scores))} 最低={fmt(min(sel_scores))} 最高={fmt(max(sel_scores))}")
    print(f"    五轴：均={fmt(mean(pos_vals))} 强={strengths.get('strong',0)} 中={strengths.get('medium',0)} 弱+无={strengths.get('weak',0)+strengths.get('absent',0)}")
    print(f"    期刊：法学研究={journals.get('法学研究',0)} 中国法学={journals.get('中国法学',0)} 社科={journals.get('中国社会科学',0)}")
    print(f"    学科覆盖：{len(discs)} 个")
    print()

# 重叠度
print(f"### 4.3 策略间重叠度\n")
pid_sets = {name: set(pid for pid,_,_,_ in sel) for name, sel in strategies.items()}
names = list(pid_sets)
for i in range(len(names)):
    for j in range(i+1,len(names)):
        ov = len(pid_sets[names[i]] & pid_sets[names[j]])
        print(f"  {names[i]} ∩ {names[j]}: {ov}/50")

# 落选分析
print(f"\n### 4.4 策略B落选分析（六维高但五轴<8）\n")
sel_b_pids = set(pid for pid,_,_,_ in sel_b)
top50_raw = sorted(valid.items(), key=lambda x: -x[1]["final_score"])[:50]
missed = [(pid,d) for pid,d in top50_raw if d["pos_total"] < 8]
print(f"  六维Top50中因五轴<8被排除的：{len(missed)} 篇")
for pid,d in missed:
    print(f"    PID={pid}  六维={fmt(d['final_score'])}  五轴={d['pos_total']}  {d['discipline']}  {d['title'][:35]}")

low_pos_high = [(pid,d) for pid,d in valid.items() if d["pos_total"] < 8]
low_pos_high.sort(key=lambda x: -x[1]["final_score"])
print(f"\n  五轴<8 但六维最高的（前10）：")
for pid,d in low_pos_high[:10]:
    print(f"    PID={pid}  六维={fmt(d['final_score'])}  五轴={d['pos_total']}  {d['discipline']}  {d['title'][:35]}")

# 保底影响
print(f"\n### 4.5 保底机制影响（策略B）\n")
sel_b_by_disc = defaultdict(list)
for pid,s,disc,_ in sel_b: sel_b_by_disc[disc].append(s)
for d in sorted(quotas, key=lambda x: -quotas[x]):
    q = quotas[d]
    raw = raw_q[d]
    pool = sum(1 for pid,dd in valid.items() if dd["discipline"]==d and dd["pos_total"]>=8)
    min_s = fmt(min(sel_b_by_disc.get(d,[0]))) if sel_b_by_disc.get(d) else "N/A"
    marker = " ← 保底提升" if q > raw + 0.5 else (" ← 被压缩" if q < raw - 0.5 else "")
    print(f"  {d}: 配额={q}(比例={fmt(raw,1)}) 池={pool} 入选最低={min_s}{marker}")

# 年度分布
print(f"\n### 4.6 策略B入选年度分布\n")
sel_b_years = Counter(valid[pid]["year"] for pid,_,_,_ in sel_b)
for y in sorted(sel_b_years):
    print(f"  {y}: {sel_b_years[y]} 篇")

print(f"\n分析完成。")
