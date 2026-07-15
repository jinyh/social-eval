#!/usr/bin/env python3
"""用 core_ceiling_bonus 重算 Top50 比例配额清单。

输入：results/rankings/e2-ccb-v5/ranking.json（已由 rebuild_ranking_v5_ccb.py 重生为 ccb）
配额：复用旧 top50-proportional.json 的 discipline_quotas（基于全库 1920 篇学科比例，
      与池成员无关，保持不变）
逻辑：每个学科从新池成员中按 ccb weighted_score 降序取前 quota[s] 篇（不足则取全部）；
      全局再按 ccb 降序排名。

输出：results/rankings/e2-ccb-v5/top50-proportional.json（重写，score=ccb）

用法：
    python3 scripts/rebuild_top50_proportional_ccb.py
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RANKING_DIR = PROJECT_ROOT / "results" / "rankings" / "e2-ccb-v5"
RANKING_JSON = RANKING_DIR / "ranking.json"
OLD_TOP50 = RANKING_DIR / "top50-proportional.json"
OUT_JSON = OLD_TOP50


def main():
    ranking = json.loads(RANKING_JSON.read_text(encoding="utf-8"))
    papers = ranking["papers"]
    by_cat: dict[str, list] = {}
    for p in papers:
        cat = p.get("metadata", {}).get("category", "") or ""
        by_cat.setdefault(cat, []).append(p)

    # 复用旧配额（全库比例，与池无关）
    old = json.loads(OLD_TOP50.read_text(encoding="utf-8"))
    quotas: dict[str, int] = old["discipline_quotas"]

    selected = []
    underflow = {}
    for cat, q in quotas.items():
        members = sorted(by_cat.get(cat, []), key=lambda x: -x["weighted_score"])
        take = min(q, len(members))
        if take < q:
            underflow[cat] = (take, q)
        selected.extend(members[:take])

    # 全局按 ccb 降序排名
    selected.sort(key=lambda x: -x["weighted_score"])

    out_papers = []
    for i, p in enumerate(selected, 1):
        m = p.get("metadata", {})
        dims = p.get("dimensions", {})
        dim_out = {}
        for dk, dd in dims.items():
            dim_out[dk] = {
                "name_zh": dd.get("name_zh", ""),
                "pooled_avg": dd.get("pooled_avg"),
                "pooled_std": dd.get("pooled_std"),
            }
        out_papers.append(
            {
                "rank": i,
                "pid": p["pid"],
                "pid_padded": str(p["pid"]),
                "category": m.get("category", ""),
                "journal": m.get("journal", ""),
                "year": m.get("year", ""),
                "title": m.get("title", ""),
                "author": (m.get("author", "") or "").split("[")[0],
                "institution": (m.get("institution", "") or "").strip("[]"),
                "score": p["weighted_score"],
                "std": p["weighted_std"],
                "metadata_author": m.get("author", ""),
                "metadata_institution": m.get("institution", ""),
                "issue": m.get("issue", ""),
                "source": p.get("source", ""),
                "dimensions": dim_out,
                "weighted_score_full": p["weighted_score"],
                "weighted_std_full": p["weighted_std"],
            }
        )

    # 学科/期刊/年度分布
    import collections
    disc_dist = collections.Counter(p["category"] for p in out_papers)
    jour_dist = collections.Counter(p["journal"] for p in out_papers)
    year_dist = collections.Counter(p["year"] for p in out_papers)

    out = {
        "metadata": {
            "description": "Top 50 proportional ranking by full-corpus discipline allocation (core_ceiling_bonus)",
            "allocation_base": "full 1920-paper discipline distribution",
            "allocation_method": "discipline quota proportional to full-corpus distribution",
            "score_range": [
                out_papers[0]["score"] if out_papers else 0,
                out_papers[-1]["score"] if out_papers else 0,
            ],
            "total": len(out_papers),
            "scoring_method": "core_ceiling_bonus",
            "underflow": underflow,
        },
        "discipline_quotas": quotas,
        "journal_distribution": dict(jour_dist),
        "year_distribution": dict(year_dist),
        "discipline_distribution": dict(disc_dist),
        "papers": out_papers,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {OUT_JSON.relative_to(PROJECT_ROOT)}（{len(out_papers)} 篇）")
    print(f"score 范围: {out['metadata']['score_range']}")
    if underflow:
        print(f"学科不足: {underflow}")
    print(f"Top5: {[(p['pid'],p['score']) for p in out_papers[:5]]}")


if __name__ == "__main__":
    main()
