#!/usr/bin/env python3
"""用 core_ceiling_bonus 协议重选 E2 候选池。

E1 候选选取口径：core_ceiling_bonus（src/reporting/scoring.py:calculate_weighted_total
+ law-v2.56.6 的 scoring_protocol）。硬条件 五轴≥9 且 E1_ccb≥80；Top80 按 ccb 降序；
学科保底≥5、年度保底≥5（从五轴≥9 宽池按 ccb 补入，匹配现行 117 池规则）。
学科分类用 sandakan 的 专家分类（33 篇专家纠正）优先，否则 原分类。

输出：
  results/rankings/e2-ccb-v5/pool.json   重写（e1_score=ccb，109 篇左右）
  results/reports/current/e2-pool-diff.md  旧池 vs 新 ccb 池的逐篇进出

用法：
    python3 scripts/reselect_e2_pool_ccb.py
"""

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.registry import load_scoring_protocol  # noqa: E402
from src.reporting.scoring import calculate_weighted_total  # noqa: E402

DIM_KEY = {
    "研究创新性": "problem_originality",
    "现状洞察度": "literature_insight",
    "理论建构力": "analytical_framework",
    "逻辑连贯性": "logical_coherence",
    "学术共识度": "conclusion_consensus",
    "前瞻延展性": "forward_extension",
}
DIMS_ZH = list(DIM_KEY.keys())

DATASET_DIR = PROJECT_ROOT / "results" / "datasets" / "three-journals"
E1_CSV = DATASET_DIR / "six-dimension" / "phase2-r2-v2.55" / "summary.csv"
FIVE_AXIS_CSV = DATASET_DIR / "five-axis" / "position-v0.2" / "summary.csv"
SANDAKAN_CSV = DATASET_DIR / "classification.csv"
META_CSV = DATASET_DIR / "metadata.csv"

TOP_N = 80
DISC_MIN = 5
YEAR_MIN = 5
E1_THRESHOLD = 80.0
AXIS5_THRESHOLD = 9
YEAR_RANGE = range(2015, 2026)

# Top50 学科配额（按全库 1920 篇学科比例）。学科保底下限取 max(DISC_MIN, 配额)，
# 确保池内各学科够 Top50 选取（避免 Top80 自然名额不足配额的学科 underflow）。
TOP50_QUOTAS = {
    "民商法学": 12, "刑法学": 9, "宪法学与行政法学": 6, "诉讼法学": 6,
    "法学理论": 6, "知识产权法学": 2, "国际法学": 2, "环境与资源保护法学": 2,
    "经济法学": 2, "法律史": 2, "党内法规学": 1,
}

OUT_POOL = PROJECT_ROOT / "results" / "rankings" / "e2-ccb-v5" / "pool.json"
OUT_DIFF = PROJECT_ROOT / "results" / "reports" / "current" / "e2-pool-diff.md"
OLD_POOL_BASELINE = OUT_POOL


def load_e1_dims() -> dict[int, dict[str, float]]:
    out = {}
    with open(E1_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = int(row["paper_id"])
            out[pid] = {DIM_KEY[k]: float(row[k]) for k in DIMS_ZH}
    return out


def load_axis5() -> dict[int, float]:
    out = {}
    with open(FIVE_AXIS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                out[int(row["paper_id"])] = float(row["五轴总分"])
            except (KeyError, ValueError):
                continue
    return out


def load_meta() -> dict[int, dict]:
    subject = {}
    year = {}
    with open(SANDAKAN_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = int(row["编号"])
            # 规范口径：专家分类优先，否则原分类（AI 主分类已弃用并从文件删除）
            subj = (row.get("专家分类") or "").strip() or (row.get("原分类") or "").strip()
            subject[pid] = subj
            year[pid] = (row.get("年份") or "").strip()
    info = {}
    with open(META_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = int(row["编号"])
            info[pid] = {
                "title": row.get("题目", ""),
                "journal": row.get("期刊", ""),
                "author": row.get("作者", ""),
                "year": row.get("年份", ""),
            }
    return {"subject": subject, "year": year, "info": info}


def select_pool(e1_dims, axis5, meta, protocol):
    ccb = {pid: calculate_weighted_total(d, protocol) for pid, d in e1_dims.items()}
    elig = [p for p in e1_dims if axis5.get(p, 0) >= AXIS5_THRESHOLD and ccb[p] >= E1_THRESHOLD]
    wide = [p for p in e1_dims if axis5.get(p, 0) >= AXIS5_THRESHOLD]  # 五轴≥9 宽池（保底用）

    pool = []
    in_pool = set()
    for pid in sorted(elig, key=lambda p: -ccb[p])[:TOP_N]:
        pool.append(pid)
        in_pool.add(pid)

    by_subj: dict[str, list[int]] = {}
    for pid in wide:
        by_subj.setdefault(meta["subject"].get(pid, ""), []).append(pid)
    for s in by_subj:
        by_subj[s].sort(key=lambda p: -ccb[p])
    subj_added = []
    for s, lst in by_subj.items():
        floor = max(DISC_MIN, TOP50_QUOTAS.get(s, DISC_MIN))
        cnt = sum(1 for p in lst if p in in_pool)
        for p in lst:
            if cnt >= floor:
                break
            if p not in in_pool:
                pool.append(p)
                in_pool.add(p)
                subj_added.append((p, s))
                cnt += 1

    by_year: dict[str, list[int]] = {}
    for pid in wide:
        by_year.setdefault(meta["year"].get(pid, ""), []).append(pid)
    for y in by_year:
        by_year[y].sort(key=lambda p: -ccb[p])
    year_added = []
    for y, lst in by_year.items():
        cnt = sum(1 for p in lst if p in in_pool)
        for p in lst:
            if cnt >= YEAR_MIN:
                break
            if p not in in_pool:
                pool.append(p)
                in_pool.add(p)
                year_added.append((p, y))
                cnt += 1

    return pool, {"eligible": len(elig), "wide": len(wide), "ccb": ccb,
                  "subj_added": subj_added, "year_added": year_added}


def main():
    protocol = load_scoring_protocol()
    print(f"scoring_protocol.mode = {protocol.get('mode')}")

    e1_dims = load_e1_dims()
    axis5 = load_axis5()
    meta = load_meta()

    # 上一版规范池仅用于输出变更对比；不影响当前重选。
    import subprocess
    try:
        r = subprocess.run(["git", "show", "HEAD:results/rankings/e2-ccb-v5/pool.json"],
                           cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        old = json.loads(r.stdout)
    except Exception:
        old = json.load(open(OLD_POOL_BASELINE, encoding="utf-8")) if OLD_POOL_BASELINE.exists() else []
    old_ids = {int(p["id"]) for p in old}
    old_score = {int(p["id"]): float(p["e1_score"]) for p in old}

    pool, stats = select_pool(e1_dims, axis5, meta, protocol)
    ccb = stats["ccb"]
    print(f"硬条件合格池(五轴≥9 且 ccb≥80): {stats['eligible']} (五轴≥9 宽池 {stats['wide']})")
    print(f"Top80 + 学科保底 {len(stats['subj_added'])} + 年度保底 {len(stats['year_added'])} "
          f"→ 最终池 {len(pool)} 篇")

    records = []
    for pid in pool:
        info = meta["info"].get(pid, {})
        records.append({
            "id": pid,
            "e1_score": round(ccb[pid], 2),
            "axis5_total": axis5.get(pid, 0),
            "subject": meta["subject"].get(pid, ""),
            "year": int(meta["info"].get(pid, {}).get("year") or 0) or None,
            "title": info.get("title", ""),
            "journal": info.get("journal", ""),
            "author": info.get("author", ""),
        })
    OUT_POOL.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {OUT_POOL.relative_to(PROJECT_ROOT)}（{len(records)} 篇）")

    # 对照清单
    new_ids = set(pool)
    added = sorted(new_ids - old_ids, key=lambda p: -ccb[p])
    removed = sorted(old_ids - new_ids, key=lambda p: -old_score.get(p, 0))
    lines = [
        "# E2 候选池重选对照（E1 口径：简单均值 → core_ceiling_bonus）\n",
        f"分类口径：sandakan 专家分类(优先) → 原分类。\n",
        f"- 旧池（简单均值）：{len(old_ids)} 篇\n",
        f"- 新池（ccb）：{len(new_ids)} 篇\n",
        f"- 新增 {len(added)} / 剔除 {len(removed)} / 保留 {len(new_ids & old_ids)}\n\n",
        f"## 新增（{len(added)} 篇）\n\n",
        "| pid | 题目 | 学科 | 年份 | 旧分(均值) | 新分(ccb) |\n|---|---|---|---|---|---|\n",
    ]
    for pid in added:
        info = meta["info"].get(pid, {})
        lines.append(f"| {pid} | {info.get('title','')[:30]} | {meta['subject'].get(pid,'')} | "
                     f"{meta['info'].get(pid,{}).get('year','')} | {old_score.get(pid,'—')} | {round(ccb[pid],2)} |\n")
    lines.append(f"\n## 剔除（{len(removed)} 篇）\n\n")
    lines.append("| pid | 题目 | 学科 | 年份 | 旧分(均值) | 新分(ccb) |\n|---|---|---|---|---|---|\n")
    for pid in removed:
        info = meta["info"].get(pid, {})
        new_s = ccb.get(pid)
        lines.append(f"| {pid} | {info.get('title','')[:30]} | {meta['subject'].get(pid,'')} | "
                     f"{meta['info'].get(pid,{}).get('year','')} | {old_score.get(pid,'—')} | "
                     f"{round(new_s,2) if new_s else '—'} |\n")
    OUT_DIFF.write_text("".join(lines), encoding="utf-8")
    print(f"已写入 {OUT_DIFF.relative_to(PROJECT_ROOT)}（新增 {len(added)} / 剔除 {len(removed)}）")


if __name__ == "__main__":
    main()
