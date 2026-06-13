#!/usr/bin/env python3
"""Generate position-first, discipline-proportional Top50 artifacts.

Rule:
1. Use papers with five-axis position score = 10 as the primary eligible pool.
2. Allocate Top50 quotas by the full-corpus discipline proportions already used
   by the project.
3. Rank within each discipline by the six-dimension weighted innovation score.
4. If a discipline lacks enough score-10 papers, fill from score-9 papers in
   that discipline and mark the inclusion reason.
5. Never include papers with position score <= 8.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RANKING_PATH = ROOT / "results" / "top101" / "ranking.json"
POSITION_DIR = ROOT / "results" / "top101-position-assessment-v0.2" / "merged"
OLD_TOP50_PATH = ROOT / "results" / "top101" / "top50-proportional.json"
OUT_JSON = ROOT / "results" / "top101" / "top50-position-first-proportional.json"
OUT_CSV = ROOT / "results" / "top101" / "top50-position-first-proportional.csv"
OUT_MD = ROOT / "results" / "top101" / "top50-position-first-proportional.md"

DISCIPLINE_QUOTAS = {
    "民商法学": 12,
    "刑法学": 9,
    "宪法学与行政法学": 6,
    "诉讼法学": 6,
    "法学理论": 6,
    "知识产权法学": 2,
    "国际法学": 2,
    "环境与资源保护法学": 2,
    "经济法学": 2,
    "法律史": 2,
    "党内法规学": 1,
}

AXIS_ZH = {
    "object_belonging": "对象归属度",
    "material_belonging": "材料归属度",
    "category_autonomy": "范畴自主度",
    "explanatory_orientation": "解释目标归属度",
    "system_mappability": "体系映射度",
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def position_result(pid: int) -> dict[str, Any]:
    path = POSITION_DIR / f"paper-{pid}.json"
    data = read_json(path)
    final = data.get("final") or {}
    axis_scores = {}
    for key, name_zh in AXIS_ZH.items():
        payload = (final.get("axis_scores") or {}).get(key, {})
        axis_scores[key] = {
            "name_zh": name_zh,
            "score": int(payload.get("score", 0)),
            "score_range": payload.get("score_range"),
        }
    return {
        "total_score": int(final.get("total_score", 0)),
        "strength": final.get("strength"),
        "agreement_level": final.get("agreement_level"),
        "review_required": bool(final.get("review_required")),
        "research_route": (final.get("research_route") or {}).get("primary"),
        "axis_scores": axis_scores,
    }


def clean_author(value: str) -> str:
    return value.split("[", 1)[0].strip()


def clean_institution(value: str) -> str:
    value = value.strip()
    if value.startswith("[1]"):
        value = value[3:]
    return value


def compact_dimensions(dimensions: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, payload in dimensions.items():
        result[key] = {
            "name_zh": payload.get("name_zh"),
            "pooled_avg": payload.get("pooled_avg"),
            "pooled_std": payload.get("pooled_std"),
        }
    return result


def select_papers(papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        by_category[paper["metadata"]["category"]].append(paper)

    for category in by_category:
        by_category[category].sort(
            key=lambda item: (float(item["weighted_score"]), -int(item["rank"])),
            reverse=True,
        )

    selected = []
    shortfalls = {}
    for category, quota in DISCIPLINE_QUOTAS.items():
        pool10 = [
            paper
            for paper in by_category.get(category, [])
            if paper["position_assessment"]["total_score"] == 10
        ]
        chosen = pool10[:quota]
        if len(chosen) < quota:
            pool9 = [
                paper
                for paper in by_category.get(category, [])
                if paper["position_assessment"]["total_score"] == 9
            ]
            chosen.extend(pool9[: quota - len(chosen)])
        if len(chosen) < quota:
            shortfalls[category] = quota - len(chosen)

        for paper in chosen:
            paper = dict(paper)
            position_score = paper["position_assessment"]["total_score"]
            paper["quota_category"] = category
            paper["selection_reason"] = (
                "五轴归属10分主池"
                if position_score == 10
                else "五轴归属9分学科配额补足"
            )
            selected.append(paper)

    selected.sort(
        key=lambda item: (float(item["weighted_score"]), -int(item["rank"])),
        reverse=True,
    )
    for rank, paper in enumerate(selected, 1):
        paper["top50_rank"] = rank
    return selected, shortfalls


def to_output_paper(paper: dict[str, Any]) -> dict[str, Any]:
    metadata = paper.get("metadata", {})
    return {
        "rank": paper["top50_rank"],
        "pid": paper["pid"],
        "category": metadata.get("category", ""),
        "quota_category": paper["quota_category"],
        "journal": metadata.get("journal", ""),
        "year": int(metadata.get("year") or 0),
        "title": metadata.get("title", ""),
        "author": clean_author(metadata.get("author", "")),
        "institution": clean_institution(metadata.get("institution", "")),
        "score": round(float(paper["weighted_score"]), 3),
        "std": paper.get("weighted_std"),
        "source": paper.get("source", ""),
        "selection_reason": paper["selection_reason"],
        "position_total_score": paper["position_assessment"]["total_score"],
        "position_strength": paper["position_assessment"].get("strength"),
        "position_agreement": paper["position_assessment"].get("agreement_level"),
        "position_review_required": paper["position_assessment"].get("review_required"),
        "research_route": paper["position_assessment"].get("research_route"),
        "axis_scores": paper["position_assessment"]["axis_scores"],
        "dimensions": compact_dimensions(paper.get("dimensions", {})),
        "original_top101_rank": paper.get("rank"),
    }


def write_csv(papers: list[dict[str, Any]]) -> None:
    fieldnames = [
        "rank",
        "pid",
        "category",
        "quota_category",
        "journal",
        "year",
        "title",
        "author",
        "institution",
        "score",
        "std",
        "source",
        "selection_reason",
        "position_total_score",
        "object_belonging",
        "material_belonging",
        "category_autonomy",
        "explanatory_orientation",
        "system_mappability",
        "position_agreement",
        "position_review_required",
        "research_route",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for paper in papers:
            axes = paper["axis_scores"]
            row = {key: paper.get(key, "") for key in fieldnames}
            for axis in AXIS_ZH:
                row[axis] = axes[axis]["score"]
            writer.writerow(row)


def write_markdown(papers: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    lines = [
        "# Top50 归属优先 + 学科比例配额清单",
        "",
        f"生成时间：{metadata['generated_at']}",
        "",
        "## 规则",
        "",
        "- 主资格池：五轴归属总分 = 10。",
        "- 补充资格池：仅当某学科 10 分论文不足配额时，使用该学科 9 分论文补足。",
        "- 8 分及以下不进入正式 Top50。",
        "- 学科额度按 1920 篇全库学科比例分配。",
        "",
        "## 统计",
        "",
        f"- 总数：{metadata['total']}",
        f"- 分数范围：{metadata['score_range'][0]}-{metadata['score_range'][1]}",
        f"- 五轴分布：{metadata['position_score_distribution']}",
        f"- 入选来源：{metadata['selection_reason_distribution']}",
        "",
        "## 论文清单",
        "",
        "| # | PID | 学科 | 年份 | 题名 | 作者 | 六维分 | 五轴分 | 入选说明 |",
        "|---:|---:|---|---:|---|---|---:|---:|---|",
    ]
    for paper in papers:
        lines.append(
            "| {rank} | {pid} | {category} | {year} | {title} | {author} | "
            "{score:.3f} | {position_total_score} | {selection_reason} |".format(
                **paper
            )
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ranking = read_json(RANKING_PATH)
    papers = ranking["papers"]
    enriched = []
    for paper in papers:
        paper = dict(paper)
        paper["position_assessment"] = position_result(int(paper["pid"]))
        enriched.append(paper)

    selected, shortfalls = select_papers(enriched)
    output_papers = [to_output_paper(paper) for paper in selected]

    old_ids = set()
    if OLD_TOP50_PATH.exists():
        old_ids = {int(paper["pid"]) for paper in read_json(OLD_TOP50_PATH).get("papers", [])}
    new_ids = {int(paper["pid"]) for paper in output_papers}

    metadata = {
        "description": "Top50 position-first discipline-proportional ranking",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_ranking": str(RANKING_PATH.relative_to(ROOT)),
        "source_position_assessment": str(POSITION_DIR.relative_to(ROOT)),
        "selection_rule": (
            "五轴归属10分为主资格池；按1920篇全库学科比例分配Top50配额；"
            "学科内按六维创新加权分排序；10分不足时仅用9分补足；8分及以下不入选"
        ),
        "discipline_quotas": DISCIPLINE_QUOTAS,
        "shortfalls": shortfalls,
        "total": len(output_papers),
        "score_range": [
            round(max(paper["score"] for paper in output_papers), 3),
            round(min(paper["score"] for paper in output_papers), 3),
        ],
        "category_distribution": dict(Counter(paper["category"] for paper in output_papers)),
        "position_score_distribution": dict(
            Counter(str(paper["position_total_score"]) for paper in output_papers)
        ),
        "selection_reason_distribution": dict(
            Counter(paper["selection_reason"] for paper in output_papers)
        ),
        "removed_from_previous_proportional": sorted(old_ids - new_ids),
        "added_vs_previous_proportional": sorted(new_ids - old_ids),
    }

    payload = {
        "metadata": metadata,
        "papers": output_papers,
    }
    write_json(OUT_JSON, payload)
    write_csv(output_papers)
    write_markdown(output_papers, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
