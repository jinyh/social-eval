#!/usr/bin/env python3
"""用 core_ceiling_bonus 重生 E2 候选池的 ranking（E2 重新排名）。

E2 重排名口径：core_ceiling_bonus。从 E1 与 E2 的 round2_scores
median 池化每维，再 calculate_weighted_total(ccb)
算总分。分类用 sandakan 专家分类(优先)→原分类。

前置：results/rankings/e2-ccb-v5/pool.json 已由 reselect_e2_pool_ccb.py 重写为 ccb 池；
      缺 E2 的论文已补跑写入 results/rankings/e2-ccb-v5/per-paper/round2/。

输出：results/rankings/e2-ccb-v5/ranking.json（weighted_score=ccb，metadata 标注）

用法：python3 scripts/rebuild_ranking_v5_ccb.py
"""

import csv
import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.registry import load_scoring_protocol  # noqa: E402
from src.reporting.pooling import (  # noqa: E402
    DIMENSION_LABELS,
    aggregate_pool,
    pool_dimension_scores,
)
from src.reporting.scoring import calculate_weighted_total  # noqa: E402

WEIGHTS = {
    "problem_originality": 0.30,
    "literature_insight": 0.20,
    "analytical_framework": 0.15,
    "logical_coherence": 0.20,
    "conclusion_consensus": 0.10,
    "forward_extension": 0.05,
}
DIM_ZH = DIMENSION_LABELS

RESULTS = PROJECT_ROOT / "results"
DATASET = RESULTS / "datasets" / "three-journals"
POOL_JSON = RESULTS / "rankings" / "e2-ccb-v5" / "pool.json"
E1_DIR = DATASET / "six-dimension" / "phase2-r2-v2.55" / "per-paper"
E2_DIR = RESULTS / "rankings" / "e2-ccb-v5" / "per-paper" / "round2"
META_CSV = DATASET / "metadata.csv"
SANDAKAN_CSV = DATASET / "classification.csv"
OUT_JSON = RESULTS / "rankings" / "e2-ccb-v5" / "ranking.json"


def load_round2(path: Path) -> dict[str, dict[str, float]] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for dk, dd in data.get("dimensions", {}).items():
        r2 = dd.get("round2_scores", {})
        if r2:
            out[dk] = dict(r2)
    return out or None


def load_meta() -> dict[int, dict]:
    sandakan = {}
    with open(SANDAKAN_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            subj = (row.get("专家分类") or "").strip() or (row.get("原分类") or "").strip()
            sandakan[int(row["编号"])] = subj
    meta = {}
    with open(META_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = int(row["编号"])
            meta[pid] = {
                "title": row.get("题目", ""),
                "category": sandakan.get(pid, row.get("分类", "")),
                "journal": row.get("期刊", ""),
                "year": row.get("年份", ""),
                "volume": row.get("卷", ""),
                "issue": row.get("期", ""),
                "author": row.get("作者", ""),
                "institution": row.get("作者机构", ""),
                "pages": row.get("页数", ""),
            }
    return meta


def build_paper(pid: int, protocol, meta) -> dict | None:
    e1 = load_round2(E1_DIR / f"paper-{pid}.json")
    e2 = load_round2(E2_DIR / f"paper-{pid}.json")
    parts = ["E1"]
    if e2:
        parts.append("E2")
    source_label = "+".join(parts)

    dimensions = {}
    for dk in WEIGHTS:
        pools, sources = pool_dimension_scores(e1, e2, None, dk)
        if not pools:
            continue
        avg, method, n = aggregate_pool(pools, sources)
        std = round(statistics.stdev(pools), 2) if len(pools) >= 2 else 0
        round_scores = {}
        if e1 and dk in e1:
            round_scores["E1"] = e1[dk]
        if e2 and dk in e2:
            round_scores["E2"] = e2[dk]
        dimensions[dk] = {
            "dimension": dk, "name_zh": DIM_ZH[dk],
            "pooled_avg": avg, "pooled_std": std, "pooled_n": n,
            "method": f"{method}({n}) [{'+'.join(sources)}]",
            "round_scores": round_scores,
        }
    if not dimensions:
        return None

    pooled = {dk: dimensions[dk]["pooled_avg"] for dk in dimensions}
    weighted = calculate_weighted_total(pooled, protocol)  # ccb
    weighted_std = sum(WEIGHTS[dk] * dimensions[dk]["pooled_std"]
                       for dk in WEIGHTS if dk in dimensions)
    m = meta.get(pid, {})
    return {
        "pid": pid, "source": source_label,
        "weighted_score": round(weighted, 4),
        "weighted_std": round(weighted_std, 2),
        "dimensions": dimensions, "metadata": m,
    }


def main():
    protocol = load_scoring_protocol()
    meta = load_meta()
    pool_ids = [p["id"] for p in json.loads(POOL_JSON.read_text(encoding="utf-8"))]
    print(f"候选池 {len(pool_ids)} 篇，scoring_protocol={protocol.get('mode')}")

    papers = []
    missing = []
    source_counts = {}
    for pid in pool_ids:
        if not (E2_DIR / f"paper-{pid}.json").exists():
            missing.append(pid)
        p = build_paper(pid, protocol, meta)
        if p is None:
            print(f"  ⚠ pid {pid} 无可用维度分")
            continue
        papers.append(p)
        source_counts[p["source"]] = source_counts.get(p["source"], 0) + 1
    if missing:
        print(f"  ⚠ 缺 E2（补跑未完成？）: {missing}")

    papers.sort(key=lambda x: -x["weighted_score"])
    for i, p in enumerate(papers, 1):
        p["rank"] = i

    ranking = {
        "metadata": {
            "description": f"E2 候选池 {len(papers)} 篇 — E1 候选选取与 E2 重排名均用 core_ceiling_bonus",
            "total": len(papers),
            "weights": WEIGHTS,
            "e1_method": "core_ceiling_bonus",
            "ranking_method": "core_ceiling_bonus (median 池化六维)",
            "aggregation_rule": "单源→mean; 双源→median; 三源→median",
            "classification": "sandakan 专家分类(优先)→原分类",
            "source_distribution": source_counts,
        },
        "papers": papers,
    }
    OUT_JSON.write_text(json.dumps(ranking, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {OUT_JSON.relative_to(PROJECT_ROOT)}（{len(papers)} 篇）")
    print(f"来源分布: {source_counts}")
    print(f"Top5: {[(p['pid'],p['weighted_score']) for p in papers[:5]]}")


if __name__ == "__main__":
    main()
