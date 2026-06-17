#!/usr/bin/env python3
"""生成项目成果报告 v4 所需的全部统计数据（使用更新后的学科分类）"""

import csv, json, math
from collections import defaultdict, Counter
from pathlib import Path

# === 工具 ===
def mean(xs): return sum(xs)/len(xs) if xs else 0
def std(xs):
    if len(xs) < 2: return 0
    m = mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))
def median(xs):
    s = sorted(xs); n = len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
def pct(xs, p):
    s = sorted(xs); n = len(s); k = (n-1)*p/100; f = int(k); c = min(f+1, n-1)
    return s[f] + (k-f)*(s[c]-s[f])
def fmt(x, d=2): return f"{x:.{d}f}"
def corr(xs, ys):
    n = len(xs)
    if n < 3: return 0
    mx, my = mean(xs), mean(ys)
    sxx = sum((x-mx)**2 for x in xs); syy = sum((y-my)**2 for y in ys)
    sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    return sxy/math.sqrt(sxx*syy) if sxx and syy else 0

ROUTE_ZH = {
    "chinese_doctrinal": "中国教义学", "comparative_localization": "比较法本土化",
    "china_practice_governance": "中国实践治理", "chinese_legal_theory": "中国法学理论",
    "traditional_resource_transform": "传统资源转化", "weakly_related": "弱相关",
    "interdisciplinary_china_data": "跨学科中国数据",
}
DIM_KEYS = ["problem_originality","literature_insight","analytical_framework",
            "logical_coherence","conclusion_consensus","forward_extension"]
DIM_ZH = {"problem_originality":"研究创新性","literature_insight":"现状洞察度",
          "analytical_framework":"理论建构力","logical_coherence":"逻辑连贯性",
          "conclusion_consensus":"学术共识度","forward_extension":"前瞻延展性"}

# === 加载 ===
print("加载数据...", flush=True)

# 元数据
meta = {}
with open("results/sandakan-new-metadata.csv", "r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f): meta[int(row["编号"])] = row

# report.md
data = {}
with open("results/fullpaper-position-assessment-stage0/report.md") as f:
    in_table = False
    for line in f:
        line = line.strip()
        if line.startswith("| PID |"): in_table = True; continue
        if in_table and line.startswith("|---"): continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 11:
                pid = int(cols[0])
                data[pid] = {
                    "year": int(cols[1]) if cols[1] else 0,
                    "journal": cols[2],
                    "six_score": float(cols[3]) if cols[3] else None,
                    "pos_score": int(cols[4]) if cols[4] else 0,
                    "strength": cols[5], "route": cols[6],
                    "r2_mode": cols[7], "precheck": cols[8],
                    "review": cols[9] == "是", "title": cols[10],
                    "discipline": meta.get(pid, {}).get("分类", ""),
                    "author": meta.get(pid, {}).get("作者", ""),
                    "institution": meta.get(pid, {}).get("作者机构", ""),
                }

# unified_rankings (逐维度)
with open("results/unified_rankings.json") as f:
    unified = {p["pid"]: p for p in json.load(f)["all_papers"]}

# 合并逐维度数据
for pid in data:
    if pid in unified:
        data[pid]["dim_avgs"] = unified[pid].get("dim_avgs", {})
        data[pid]["dim_stds"] = unified[pid].get("dim_stds", {})

valid = {pid: d for pid, d in data.items() if d["six_score"] is not None}
print(f"  元数据: {len(meta)}, report: {len(data)}, 有效: {len(valid)}", flush=True)

out = []
def p(s=""): out.append(s)

# ============================================================
# 一、预检分析
# ============================================================
p("=" * 60)
p("一、预检分析")
p("=" * 60)

# 1.1 总体
precheck_zh = {
    "enter_six_dimension_review": "进入六维评审",
    "boundary_review": "边界复核",
    "majority_reject": "多数拒绝",
    "single_reject": "单模型拒绝",
    "obviously_ineligible": "明显不适格",
}
pc = Counter(d["precheck"] for d in data.values())
p("\n### 1.1 预检总体分布\n")
p("| 预检状态 | 篇数 | 占比 |")
p("|----------|------|------|")
for status in ["enter_six_dimension_review","boundary_review","majority_reject","single_reject","obviously_ineligible"]:
    cnt = pc.get(status, 0)
    p(f"| {precheck_zh[status]} | {cnt} | {fmt(cnt/len(data)*100,1)}% |")

pass_rate = pc.get("enter_six_dimension_review", 0) / len(data) * 100
p(f"\n通过率（进入六维评审）：**{fmt(pass_rate,1)}%**")

# 1.2 年度
p("\n### 1.2 预检年度分布\n")
p("| 年份 | 总数 | 通过 | 通过率 | 边界 | 拒绝 |")
p("|------|------|------|--------|------|------|")
for y in sorted(set(d["year"] for d in data.values())):
    total = sum(1 for d in data.values() if d["year"]==y)
    passed = sum(1 for d in data.values() if d["year"]==y and d["precheck"]=="enter_six_dimension_review")
    boundary = sum(1 for d in data.values() if d["year"]==y and d["precheck"]=="boundary_review")
    rejected = total - passed - boundary
    p(f"| {y} | {total} | {passed} | {fmt(passed/total*100,1)}% | {boundary} | {rejected} |")

# 1.3 期刊
p("\n### 1.3 预检期刊分布\n")
p("| 期刊 | 总数 | 通过 | 通过率 | 边界 | 拒绝 |")
p("|------|------|------|--------|------|------|")
for j in ["中国法学","法学研究","中国社会科学"]:
    total = sum(1 for d in data.values() if d["journal"]==j)
    passed = sum(1 for d in data.values() if d["journal"]==j and d["precheck"]=="enter_six_dimension_review")
    boundary = sum(1 for d in data.values() if d["journal"]==j and d["precheck"]=="boundary_review")
    rejected = total - passed - boundary
    p(f"| {j} | {total} | {passed} | {fmt(passed/total*100,1)}% | {boundary} | {rejected} |")

# 1.4 学科
p("\n### 1.4 预检学科分布\n")
p("| 学科 | 总数 | 通过 | 通过率 |")
p("|------|------|------|--------|")
disc_all = Counter(d["discipline"] for d in data.values())
disc_pass = Counter(d["discipline"] for d in data.values() if d["precheck"]=="enter_six_dimension_review")
for disc in sorted(disc_all, key=lambda x: -disc_all[x]):
    t = disc_all[disc]; pa = disc_pass.get(disc, 0)
    p(f"| {disc} | {t} | {pa} | {fmt(pa/t*100,1)}% |")

# ============================================================
# 二、五轴位置归属度
# ============================================================
p("\n" + "=" * 60)
p("二、五轴位置归属度评估结果（1920 篇全量）")
p("=" * 60)

pos_scores = [d["pos_score"] for d in valid.values()]

# 2.1 总体
p("\n### 2.1 总体统计\n")
p(f"| 指标 | 数值 |")
p(f"|------|------|")
p(f"| 评估对象 | 法学三大刊 2015–2025 年 {len(valid)} 篇 |")
p(f"| 总分均值 | **{fmt(mean(pos_scores))}** / 10 |")
p(f"| 总分中位数 | {fmt(median(pos_scores))} |")
p(f"| 强归属（8–10） | {sum(1 for s in pos_scores if s>=8)} 篇（{fmt(sum(1 for s in pos_scores if s>=8)/len(valid)*100,1)}%） |")
p(f"| 中归属（5–7） | {sum(1 for s in pos_scores if 5<=s<=7)} 篇 |")
p(f"| 弱归属（2–4） | {sum(1 for s in pos_scores if 2<=s<=4)} 篇 |")
p(f"| 无归属（0–1） | {sum(1 for s in pos_scores if s<=1)} 篇 |")

# 2.2 总分分布
p("\n### 2.2 总分分布\n")
p("| 分数 | 篇数 | 占比 | 说明 |")
p("|------|------|------|------|")
c = Counter(pos_scores)
for s in range(10, -1, -1):
    cnt = c.get(s, 0)
    note = ""
    if s == 10: note = "五轴均有核心结构证据"
    elif s >= 8: note = "强归属"
    elif s >= 5: note = "中归属"
    elif s >= 2: note = "弱归属"
    else: note = "无归属"
    p(f"| {s} | {cnt} | {fmt(cnt/len(valid)*100,1)}% | {note} |")

# 2.3 年度
p("\n### 2.3 五轴年度分布\n")
p("| 年份 | N | 均值 | 满分率 | 强归属率 |")
p("|------|---|------|--------|----------|")
for y in sorted(set(d["year"] for d in valid.values())):
    vals = [d["pos_score"] for d in valid.values() if d["year"]==y]
    full_rate = sum(1 for v in vals if v==10)/len(vals)*100
    strong_rate = sum(1 for v in vals if v>=8)/len(vals)*100
    p(f"| {y} | {len(vals)} | {fmt(mean(vals))} | {fmt(full_rate,1)}% | {fmt(strong_rate,1)}% |")

# 2.4 期刊
p("\n### 2.4 五轴期刊分布\n")
p("| 期刊 | N | 均值 | 满分率 | 强归属率 |")
p("|------|---|------|--------|----------|")
for j in ["中国法学","法学研究","中国社会科学"]:
    vals = [d["pos_score"] for d in valid.values() if d["journal"]==j]
    full_rate = sum(1 for v in vals if v==10)/len(vals)*100
    strong_rate = sum(1 for v in vals if v>=8)/len(vals)*100
    p(f"| {j} | {len(vals)} | {fmt(mean(vals))} | {fmt(full_rate,1)}% | {fmt(strong_rate,1)}% |")

# 2.5 学科
p("\n### 2.5 五轴学科分布\n")
p("| 学科 | N | 均值 | 满分率 | 强归属率 |")
p("|------|---|------|--------|----------|")
for disc in sorted(set(d["discipline"] for d in valid.values()), key=lambda x: -sum(1 for d in valid.values() if d["discipline"]==x)):
    vals = [d["pos_score"] for d in valid.values() if d["discipline"]==disc]
    full_rate = sum(1 for v in vals if v==10)/len(vals)*100
    strong_rate = sum(1 for v in vals if v>=8)/len(vals)*100
    p(f"| {disc} | {len(vals)} | {fmt(mean(vals))} | {fmt(full_rate,1)}% | {fmt(strong_rate,1)}% |")

# 2.6 分歧与复核
p("\n### 2.6 分歧与复核\n")
r2c = Counter(d["r2_mode"] for d in valid.values())
p("| R2 模式 | 篇数 | 占比 | 说明 |")
p("|---------|------|------|------|")
p(f"| skip | {r2c.get('skip',0)} | {fmt(r2c.get('skip',0)/len(valid)*100,1)}% | 两模型一致，跳过 R2 |")
p(f"| light | {r2c.get('light',0)} | {fmt(r2c.get('light',0)/len(valid)*100,1)}% | 路径/节点分歧，轻量复核 |")
p(f"| full | {r2c.get('full',0)} | {fmt(r2c.get('full',0)/len(valid)*100,1)}% | 轴分/置信度分歧，完整复核 |")

review_cnt = sum(1 for d in valid.values() if d["review"])
p(f"\n需专家复核：**{review_cnt}** 篇（{fmt(review_cnt/len(valid)*100,1)}%）")

# ============================================================
# 三、研究路径
# ============================================================
p("\n" + "=" * 60)
p("三、研究路径分析")
p("=" * 60)

# 3.1 总体
p("\n### 3.1 总体分布\n")
p("| 路径 | 篇数 | 占比 |")
p("|------|------|------|")
rc = Counter(d["route"] for d in valid.values())
for r, cnt in rc.most_common():
    p(f"| {ROUTE_ZH.get(r,r)} | {cnt} | {fmt(cnt/len(valid)*100,1)}% |")

# 3.2 年度
p("\n### 3.2 研究路径年度趋势\n")
main_routes = ["chinese_doctrinal","china_practice_governance","comparative_localization","chinese_legal_theory"]
header = "| 年份 | 总数 |" + "|".join(f" {ROUTE_ZH[r]}" for r in main_routes) + " |"
p(header)
sep = "|------|------|" + "|".join("------" for _ in main_routes) + "|"
p(sep)
for y in sorted(set(d["year"] for d in valid.values())):
    total = sum(1 for d in valid.values() if d["year"]==y)
    row = f"| {y} | {total} |"
    for r in main_routes:
        cnt = sum(1 for d in valid.values() if d["year"]==y and d["route"]==r)
        row += f" {cnt} |"
    p(row)

# 3.3 期刊
p("\n### 3.3 研究路径期刊分布\n")
header = "| 期刊 |" + "|".join(f" {ROUTE_ZH[r]}" for r in main_routes) + " |"
p(header)
sep = "|------|" + "|".join("------" for _ in main_routes) + "|"
p(sep)
for j in ["中国法学","法学研究","中国社会科学"]:
    row = f"| {j} |"
    for r in main_routes:
        cnt = sum(1 for d in valid.values() if d["journal"]==j and d["route"]==r)
        total_j = sum(1 for d in valid.values() if d["journal"]==j)
        row += f" {cnt}({fmt(cnt/total_j*100,0)}%) |"
    p(row)

# 3.4 学科×路径
p("\n### 3.4 学科×研究路径交叉（前四路径）\n")
header = "| 学科 | N |" + "|".join(f" {ROUTE_ZH[r]}" for r in main_routes) + " | 主路径 |"
p(header)
sep = "|------|---|" + "|".join("------" for _ in main_routes) + "|------|"
p(sep)
for disc in sorted(set(d["discipline"] for d in valid.values()), key=lambda x: -sum(1 for d in valid.values() if d["discipline"]==x)):
    total = sum(1 for d in valid.values() if d["discipline"]==disc)
    row = f"| {disc} | {total} |"
    best_r = ""
    best_c = 0
    for r in main_routes:
        cnt = sum(1 for d in valid.values() if d["discipline"]==disc and d["route"]==r)
        row += f" {cnt} |"
        if cnt > best_c: best_c = cnt; best_r = ROUTE_ZH.get(r,r)
    row += f" {best_r} |"
    p(row)

# ============================================================
# 四、六维评价
# ============================================================
p("\n" + "=" * 60)
p("四、六维评价全量分析")
p("=" * 60)

six_scores = [d["six_score"] for d in valid.values()]

# 4.1 各维度统计
p("\n### 4.1 各维度统计（基于统一排名聚合）\n")
p("| 维度 | 均值 | 中位数 | std | P25 | P75 | Min | Max |")
p("|------|------|--------|-----|-----|-----|-----|-----|")
for dk in DIM_KEYS:
    vals = [d["dim_avgs"].get(dk, 0) for d in valid.values() if d.get("dim_avgs")]
    if vals:
        p(f"| {DIM_ZH[dk]} | {fmt(mean(vals))} | {fmt(median(vals))} | {fmt(std(vals))} | {fmt(pct(vals,25))} | {fmt(pct(vals,75))} | {fmt(min(vals))} | {fmt(max(vals))} |")

# 4.2 总分
p("\n### 4.2 加权总分分布\n")
p(f"- N = {len(six_scores)}")
p(f"- 均值 = {fmt(mean(six_scores))}")
p(f"- 中位数 = {fmt(median(six_scores))}")
p(f"- 标准差 = {fmt(std(six_scores))}")
p(f"- P10 = {fmt(pct(six_scores,10))}，P25 = {fmt(pct(six_scores,25))}，P75 = {fmt(pct(six_scores,75))}，P90 = {fmt(pct(six_scores,90))}")
p(f"- 范围 = [{fmt(min(six_scores))}, {fmt(max(six_scores))}]")

p("\n| 分档 | 范围 | 篇数 | 占比 |")
p("|------|------|------|------|")
for lo,hi,label in [(0,30,"极差"),(30,45,"差"),(45,55,"中下"),(55,65,"中等"),(65,75,"良好"),(75,85,"优秀"),(85,100,"卓越")]:
    cnt = sum(1 for s in six_scores if lo <= s < hi)
    p(f"| {label} | {lo}–{hi} | {cnt} | {fmt(cnt/len(six_scores)*100,1)}% |")

# 4.3 年度
p("\n### 4.3 六维年度趋势\n")
p("| 年份 | N | 均值 | 中位数 | std | P25 | P75 |")
p("|------|---|------|--------|-----|-----|-----|")
for y in sorted(set(d["year"] for d in valid.values())):
    vals = [d["six_score"] for d in valid.values() if d["year"]==y]
    p(f"| {y} | {len(vals)} | {fmt(mean(vals))} | {fmt(median(vals))} | {fmt(std(vals))} | {fmt(pct(vals,25))} | {fmt(pct(vals,75))} |")

# 4.4 期刊
p("\n### 4.4 六维期刊分布\n")
p("| 期刊 | N | 均值 | 中位数 | std | ≥75分 |")
p("|------|---|------|--------|-----|-------|")
for j in ["中国法学","法学研究","中国社会科学"]:
    vals = [d["six_score"] for d in valid.values() if d["journal"]==j]
    n75 = sum(1 for v in vals if v>=75)
    p(f"| {j} | {len(vals)} | {fmt(mean(vals))} | {fmt(median(vals))} | {fmt(std(vals))} | {n75} ({fmt(n75/len(vals)*100,1)}%) |")

# 4.5 学科
p("\n### 4.5 六维学科分布\n")
p("| 学科 | N | 均值 | 中位数 | std | ≥75分 |")
p("|------|---|------|--------|-----|-------|")
for disc in sorted(set(d["discipline"] for d in valid.values()), key=lambda x: -sum(1 for d in valid.values() if d["discipline"]==x)):
    vals = [d["six_score"] for d in valid.values() if d["discipline"]==disc]
    n75 = sum(1 for v in vals if v>=75)
    p(f"| {disc} | {len(vals)} | {fmt(mean(vals))} | {fmt(median(vals))} | {fmt(std(vals))} | {n75} ({fmt(n75/len(vals)*100,1)}%) |")

# ============================================================
# 五、交叉分析
# ============================================================
p("\n" + "=" * 60)
p("五、六维×五轴交叉分析")
p("=" * 60)

fs = [d["six_score"] for d in valid.values()]
ps = [d["pos_score"] for d in valid.values()]
r = corr(fs, ps)
p(f"\n### 5.1 相关性\n")
p(f"六维总分 vs 五轴总分：Pearson r = {fmt(r, 3)}（{'弱' if abs(r)<0.3 else '中等'}相关）")
p(f"\n→ 两个维度测量不同属性：六维衡量学术质量，五轴衡量自主知识体系归属关系。")

# 5.2 按强度看六维
p("\n### 5.2 按五轴强度看六维分布\n")
p("| 强度 | N | 六维均分 | 六维中位 | P25 | P75 |")
p("|------|---|----------|----------|-----|-----|")
for s in ["strong","medium","weak","absent"]:
    zh = {"strong":"强","medium":"中","weak":"弱","absent":"无"}[s]
    vals = [d["six_score"] for d in valid.values() if d["strength"]==s]
    if vals:
        p(f"| {zh} | {len(vals)} | {fmt(mean(vals))} | {fmt(median(vals))} | {fmt(pct(vals,25))} | {fmt(pct(vals,75))} |")

# 5.3 路径×六维
p("\n### 5.3 研究路径×六维质量\n")
p("| 路径 | N | 六维均分 | 中位数 | ≥75分 |")
p("|------|---|----------|--------|-------|")
rs = defaultdict(list)
for d in valid.values(): rs[d["route"]].append(d["six_score"])
for r in sorted(rs, key=lambda x: -mean(rs[x])):
    vals = rs[r]
    n75 = sum(1 for v in vals if v>=75)
    p(f"| {ROUTE_ZH.get(r,r)} | {len(vals)} | {fmt(mean(vals))} | {fmt(median(vals))} | {n75} ({fmt(n75/len(vals)*100,1)}%) |")

# ============================================================
# 六、Top 50 策略 D
# ============================================================
p("\n" + "=" * 60)
p("六、Top 50 专家审阅候选清单（策略 D）")
p("=" * 60)

# 配额
EXCLUDED = set()  # v4: 数字法学已从分类中移除
disc_n = Counter(d["discipline"] for d in valid.values())
total_n = sum(n for d, n in disc_n.items() if d not in EXCLUDED)
raw_q = {}; quotas = {}
for d, n in disc_n.items():
    if d in EXCLUDED: continue
    raw_q[d] = n / total_n * 50
    quotas[d] = max(2, round(raw_q[d]))
diff = sum(quotas.values()) - 50
if diff > 0:
    for d in sorted(quotas, key=lambda x: -quotas[x]):
        if diff <= 0: break
        red = min(quotas[d] - 2, diff); quotas[d] -= red; diff -= red
elif diff < 0:
    for d in sorted(raw_q, key=lambda x: raw_q[x] - int(raw_q[x]), reverse=True):
        if diff >= 0: break
        quotas[d] += 1; diff += 1

# 分层选择
tiers = {10: [], 8: [], 0: []}
for pid, d in valid.items():
    if d["discipline"] in EXCLUDED: continue
    if d["pos_score"] == 10: tiers[10].append((pid, d))
    elif d["pos_score"] >= 8: tiers[8].append((pid, d))
    else: tiers[0].append((pid, d))
sel_d = []
tier_used = {}  # pid -> tier_key
for disc, q in quotas.items():
    rem = q
    for tk in [10, 8, 0]:
        cands = [(pid, d["six_score"]) for pid, d in tiers[tk] if d["discipline"]==disc]
        cands.sort(key=lambda x: -x[1])
        take = cands[:rem]
        for pid, s in take:
            sel_d.append((pid, s, disc))
            tier_used[pid] = tk
        rem -= len(take)
        if rem <= 0: break

sel_pids = set(pid for pid,_,_ in sel_d)
sel_scores = [s for _,s,_ in sel_d]

# 6.1 配额
p("\n### 6.1 学科配额\n")
p("| 学科 | 全库数 | 全库占比 | 纯比例 | 配额 | 入选最低分 |")
p("|------|--------|----------|--------|------|-----------|")
for d in sorted(quotas, key=lambda x: -quotas[x]):
    min_s = min(s for pid,s,disc in sel_d if disc==d)
    p(f"| {d} | {disc_n[d]} | {fmt(disc_n[d]/total_n*100,1)}% | {fmt(raw_q[d],1)} | {quotas[d]} | {fmt(min_s)} |")
p(f"| **合计** | {total_n} | 100.0% | 50.0 | **{sum(quotas.values())}** | |")

# 6.2 主表
p("\n### 6.2 候选清单主表\n")
p("> 序号为展示顺序，按六维分降序。不构成最终学术名次。\n")
p("| # | 学科 | 题目 | 作者 | 机构 | 研究路径 | 六维分 | 五轴分 |")
p("|---|------|------|------|------|----------|--------|--------|")
sel_sorted = sorted(sel_d, key=lambda x: -x[1])
for i, (pid, s, disc) in enumerate(sel_sorted, 1):
    d = valid[pid]
    inst = d["institution"]
    # 清理机构名
    if inst.startswith("[1]"): inst = inst[3:]
    author = d["author"]
    if author.startswith("[1]"): author = author[3:]
    if "," in author: author = author.split(",")[0]
    p(f"| {i} | {disc} | {d['title']} | {author} | {inst} | {ROUTE_ZH.get(d['route'],d['route'])} | {fmt(s)} | {d['pos_score']} |")

# 6.3 六维详情表
p("\n### 6.3 六维详情表\n")
p("> 格式：均分±标准差。std > 5 以 **粗体** 标记。\n")
p("| # | 题目 | 创新性 | 洞察度 | 建构力 | 连贯性 | 共识度 | 延展性 |")
p("|---|------|--------|--------|--------|--------|--------|--------|")
for i, (pid, s, disc) in enumerate(sel_sorted, 1):
    d = valid[pid]
    avgs = d.get("dim_avgs", {})
    stds = d.get("dim_stds", {})
    row = f"| {i} | {d['title'][:20]} |"
    for dk in DIM_KEYS:
        a = avgs.get(dk, 0)
        sd = stds.get(dk, 0)
        if sd > 5:
            row += f" {fmt(a,0)}±**{fmt(sd,1)}** |"
        else:
            row += f" {fmt(a,0)}±{fmt(sd,1)} |"
    p(row)

# 6.4 构成分析
p("\n### 6.4 构成分析\n")

# 期刊
p("**期刊分布**：\n")
jc = Counter(valid[pid]["journal"] for pid in sel_pids)
p("| 期刊 | 篇数 | 占比 |")
p("|------|------|------|")
for j, cnt in jc.most_common():
    p(f"| {j} | {cnt} | {fmt(cnt/50*100,1)}% |")

# 年度
p("\n**年度分布**：\n")
p("| 年份 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |")
p("|------|------|------|------|------|------|------|------|------|------|------|------|")
yc = Counter(valid[pid]["year"] for pid in sel_pids)
row = "| 篇数 |"
for y in range(2015, 2026):
    row += f" {yc.get(y,0)} |"
p(row)

# 研究路径
p("\n**研究路径分布**：\n")
rpc = Counter(valid[pid]["route"] for pid in sel_pids)
for r, cnt in rpc.most_common():
    p(f"- {ROUTE_ZH.get(r,r)}：{cnt} 篇")

# 机构
p("\n**机构分布**（≥2 篇）：\n")
ic = Counter(valid[pid]["institution"] for pid in sel_pids)
p("| 机构 | 篇数 |")
p("|------|------|")
for inst, cnt in ic.most_common():
    if cnt < 2: break
    clean = inst[3:] if inst.startswith("[1]") else inst
    p(f"| {clean} | {cnt} |")

# 作者
p("\n**入选 ≥2 篇的作者**：\n")
ac = Counter(valid[pid]["author"] for pid in sel_pids)
p("| 作者 | 篇数 | 机构 |")
p("|------|------|------|")
for a, cnt in ac.most_common():
    if cnt < 2: break
    clean = a[3:] if a.startswith("[1]") else a
    inst = valid[[pid for pid in sel_pids if valid[pid]["author"]==a][0]]["institution"]
    if inst.startswith("[1]"): inst = inst[3:]
    p(f"| {clean} | {cnt} | {inst} |")

# 6.5 门槛分析
p("\n### 6.5 各学科入选门槛\n")
p("| 学科 | 配额 | 入选最低分 | 候补第1名 | 候补六维分 |")
p("|------|------|-----------|----------|-----------|")
for disc in sorted(quotas, key=lambda x: -quotas[x]):
    disc_scores = [(pid,s) for pid,s,d in sel_d if d==disc]
    min_s = min(s for _,s in disc_scores)
    # 候补
    pool = [(pid, d["six_score"]) for pid, d in valid.items()
            if d["discipline"]==disc and pid not in sel_pids and d["discipline"] not in EXCLUDED]
    pool.sort(key=lambda x: -x[1])
    if pool:
        nxt_pid, nxt_s = pool[0]
        p(f"| {disc} | {quotas[disc]} | {fmt(min_s)} | {valid[nxt_pid]['title'][:25]} | {fmt(nxt_s)} |")
    else:
        p(f"| {disc} | {quotas[disc]} | {fmt(min_s)} | — | — |")

# 输出
with open("/tmp/report_v4_data.md", "w") as f:
    f.write("\n".join(out))
print(f"\n统计输出：/tmp/report_v4_data.md ({len(out)} 行)", flush=True)
