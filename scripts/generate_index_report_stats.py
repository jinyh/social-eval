#!/usr/bin/env python3
"""Generate statistics for the China autonomous knowledge index report.

The script keeps the report data reproducible and makes the ID alignment
explicit. It reads the current evaluation outputs and writes report-only
derived files under ``results/``.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from src.reporting.scoring import calculate_weighted_total  # noqa: E402

FRAMEWORK_YAML = ROOT / "configs" / "frameworks" / "law-v2.56.6-20260522.yaml"

METADATA_PATH = ROOT / "results" / "merged-metadata.csv"
RANKINGS_PATH = ROOT / "results" / "unified_rankings.json"
ROUND2_DIR = ROOT / "results" / "fullevaluation" / "round2"
ROUND1_ERR_PATH = (
    ROOT / "results" / "fullevaluation" / "round1-err" / "error-summary.json"
)
TOP101_RANKING_PATH = ROOT / "results" / "e2-pool" / "ranking_v5_pool.json"
TOP50_PROPORTIONAL_PATH = (
    ROOT / "results" / "e2-pool" / "top50-proportional.json"
)

OVERVIEW_OUT = ROOT / "results" / "report_overview_stats.json"
MASTER_OUT = ROOT / "results" / "report_paper_master.csv"
GROUP_STATS_OUT = ROOT / "results" / "report_group_stats.csv"
TOP_CANDIDATES_OUT = ROOT / "results" / "report_top_candidates_current.json"
ID_INTEGRITY_OUT = ROOT / "results" / "report_id_integrity.json"

DIMENSIONS = [
    ("problem_originality", "研究创新性"),
    ("literature_insight", "现状洞察度"),
    ("analytical_framework", "理论建构力"),
    ("logical_coherence", "逻辑连贯性"),
    ("conclusion_consensus", "学术共识度"),
    ("forward_extension", "前瞻延展性"),
]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def rounded(value: float | int | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round(q * (len(ordered) - 1))
    return ordered[index]


def numeric_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }

    return {
        "count": len(values),
        "mean": rounded(statistics.mean(values)),
        "median": rounded(statistics.median(values)),
        "min": rounded(min(values)),
        "p10": rounded(percentile(values, 0.10)),
        "p25": rounded(percentile(values, 0.25)),
        "p75": rounded(percentile(values, 0.75)),
        "p90": rounded(percentile(values, 0.90)),
        "p95": rounded(percentile(values, 0.95)),
        "p99": rounded(percentile(values, 0.99)),
        "max": rounded(max(values)),
    }


def parse_paper_id(value: str) -> int | None:
    value = value.strip()
    if value.startswith("paper-"):
        value = value.removeprefix("paper-")
    try:
        return int(value)
    except ValueError:
        return None


def load_metadata() -> dict[int, dict[str, str]]:
    with METADATA_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: dict[int, dict[str, str]] = {}
        for row in reader:
            pid = parse_paper_id(row.get("编号", ""))
            if pid is not None:
                rows[pid] = row
    # 叠加 sandakan 学科分类（专家分类优先，否则原分类），覆盖 merged 原分类
    sandakan_path = ROOT / "results" / "sandakan-new-metadata.csv"
    if sandakan_path.exists():
        with sandakan_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                pid = parse_paper_id(row.get("编号", ""))
                if pid is not None and pid in rows:
                    subj = (row.get("专家分类") or "").strip() or (row.get("原分类") or "").strip()
                    if subj:
                        rows[pid]["分类"] = subj
    return rows


def top101_to_unified_row(paper: dict[str, Any]) -> dict[str, Any]:
    """Convert a Top101 pooled paper row to the full-ranking row shape."""
    dimensions = paper.get("dimensions", {})
    dim_avgs = {}
    dim_stds = {}
    dim_methods = {}
    e3_merged = []
    for dim, _name_zh in DIMENSIONS:
        dim_data = dimensions.get(dim, {})
        dim_avgs[dim] = dim_data.get("pooled_avg")
        dim_stds[dim] = dim_data.get("pooled_std")
        dim_methods[dim] = dim_data.get("method", "")
        round_scores = dim_data.get("round_scores", {})
        if "E3" in round_scores:
            e3_merged.append(dim)

    return {
        "pid": int(paper["pid"]),
        "weighted_score": round(float(paper.get("weighted_score", 0)), 3),
        "weighted_std": paper.get("weighted_std"),
        "dim_avgs": dim_avgs,
        "dim_stds": dim_stds,
        "dim_methods": dim_methods,
        "source": paper.get("source", ""),
        "e2_override": True,
        "e3_merged": e3_merged,
    }


def load_top101_ranking() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = read_json(TOP101_RANKING_PATH)
    return data.get("papers", []), data.get("metadata", {})


def load_rankings() -> tuple[
    list[dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    data = read_json(RANKINGS_PATH)
    by_pid = {int(item["pid"]): dict(item) for item in data["all_papers"]}
    top101_papers, top101_metadata = load_top101_ranking()

    for paper in top101_papers:
        by_pid[int(paper["pid"])] = top101_to_unified_row(paper)

    # 统一 weighted_score 到 core_ceiling_bonus（从每行 dim_avgs 重算），
    # 覆盖基座 unified_rankings.json 的简单加权和口径。
    protocol = yaml.safe_load(FRAMEWORK_YAML.read_text(encoding="utf-8"))["scoring_protocol"]
    for paper in by_pid.values():
        dim_avgs = paper.get("dim_avgs", {})
        if dim_avgs:
            paper["weighted_score"] = calculate_weighted_total(dim_avgs, protocol)

    papers = sorted(
        by_pid.values(),
        key=lambda item: (float(item["weighted_score"]), -int(item["pid"])),
        reverse=True,
    )
    for rank, paper in enumerate(papers, 1):
        paper["rank"] = rank

    e2_count = sum(1 for paper in papers if paper.get("e2_override"))
    e3_count = sum(1 for paper in papers if paper.get("e3_merged"))
    metadata = {
        "description": "Unified E1/E2/E3 scoring with Top101 E2 candidate overlay",
        "pipeline": "E1 R2 baseline → E2 candidate pool 101 → E3 selective pool 45",
        "aggregation": "E1 only: mean(4); E1+E2: median(8); E1+E2+E3: median(12)",
        "weights": data.get("metadata", {}).get("weights", {}),
        "total_papers": len(papers),
        "e2_pooled": e2_count,
        "e3_pooled": e3_count,
        "top101_source": str(TOP101_RANKING_PATH.relative_to(ROOT)),
        "top101_metadata": top101_metadata,
        "base_source": str(RANKINGS_PATH.relative_to(ROOT)),
    }

    return papers, {int(item["pid"]): item for item in papers}, metadata


def load_round2() -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for path in sorted(ROUND2_DIR.glob("paper-*.json")):
        pid = parse_paper_id(path.stem)
        if pid is None:
            continue
        data = read_json(path)
        result[pid] = data.get("overall", {})
    return result


def load_round1_error_categories() -> tuple[dict[int, str], dict[str, Any]]:
    if not ROUND1_ERR_PATH.exists():
        return {}, {}

    data = read_json(ROUND1_ERR_PATH)
    categories: dict[int, str] = {}
    for category, papers in data.get("papers", {}).items():
        for paper in papers:
            pid = parse_paper_id(str(paper.get("paper_id", "")))
            if pid is not None:
                categories[pid] = category
    return categories, data


def load_top101_candidates(
    metadata: dict[int, dict[str, str]],
) -> dict[str, Any]:
    """Load the actual E2 candidate pool.

    The E2 pool is not recomputed from the current full-corpus ranking. The
    materialized E2 candidate pool under ``results/e2-pool/ranking_v5_pool.json`` is the
    current source of truth.
    """
    data = read_json(TOP101_RANKING_PATH)

    candidate_rows = []
    for paper in data.get("papers", []):
        pid = int(paper["pid"])
        meta = metadata.get(pid, {})
        reason = "top60" if int(paper.get("rank", 0)) <= 60 else "coverage_minimum"
        candidate_rows.append(
            {
                "pid": pid,
                "rank": paper.get("rank"),
                "score": rounded(paper.get("weighted_score")),
                "weighted_std": paper.get("weighted_std"),
                "reason": reason,
                "year": paper.get("metadata", {}).get("year") or meta.get("年份", ""),
                "journal": paper.get("metadata", {}).get("journal")
                or meta.get("期刊", ""),
                "category": paper.get("metadata", {}).get("category")
                or meta.get("分类", ""),
                "title": paper.get("metadata", {}).get("title") or meta.get("题目", ""),
                "author": paper.get("metadata", {}).get("author") or meta.get("作者", ""),
                "source": paper.get("source", ""),
                "dim_scores": {
                    dim: paper.get("dimensions", {}).get(dim, {}).get("pooled_avg")
                    for dim, _name in DIMENSIONS
                },
            }
        )

    candidate_rows.sort(key=lambda item: (int(item["rank"]), item["pid"]))
    scores = [
        float(row["score"])
        for row in candidate_rows
        if isinstance(row.get("score"), (int, float))
    ]
    weighted_stds = [
        float(row["weighted_std"])
        for row in candidate_rows
        if isinstance(row.get("weighted_std"), (int, float))
    ]
    year_counts = dict(Counter(row["year"] for row in candidate_rows))
    journal_counts = dict(Counter(row["journal"] for row in candidate_rows))
    category_counts = dict(Counter(row["category"] for row in candidate_rows))
    top60_count = sum(1 for row in candidate_rows if int(row.get("rank") or 0) <= 60)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(TOP101_RANKING_PATH.relative_to(ROOT)),
        "selection_strategy": "E2 候选池：Top60 + 每年至少 5 篇 + 每学科至少 5 篇",
        "composition": {
            "top60_count": top60_count,
            "coverage_supplement_count": len(candidate_rows) - top60_count,
            "year_minimum": min(year_counts.values()) if year_counts else 0,
            "discipline_minimum": min(category_counts.values())
            if category_counts
            else 0,
        },
        "total_candidates": len(candidate_rows),
        "score_distribution": numeric_stats(scores),
        "weighted_std_distribution": numeric_stats(weighted_stds),
        "source_distribution": data.get("metadata", {}).get("source_distribution", {}),
        "year_counts": year_counts,
        "journal_counts": journal_counts,
        "category_counts": category_counts,
        "papers": candidate_rows,
    }


def load_top50_proportional() -> dict[str, Any]:
    """Load the discipline-proportional expert-review Top50 pool."""
    if not TOP50_PROPORTIONAL_PATH.exists():
        return {
            "source": str(TOP50_PROPORTIONAL_PATH.relative_to(ROOT)),
            "metadata": {},
            "selection_strategy": "按全量 1920 篇学科占比分配 Top50 配额，在各学科内择优形成专家审阅版。",
            "total": 0,
            "score_distribution": numeric_stats([]),
            "weighted_std_distribution": numeric_stats([]),
            "weighted_std_bands": {"lte_5": 0, "lte_8": 0, "gt_8": 0},
            "discipline_quotas": {},
            "discipline_quota_total": 0,
            "journal_counts": {},
            "year_counts": {},
            "category_counts": {},
            "source_distribution": {},
            "papers": [],
        }

    data = read_json(TOP50_PROPORTIONAL_PATH)
    papers = data.get("papers", [])
    scores = [
        float(paper["score"])
        for paper in papers
        if isinstance(paper.get("score"), (int, float))
    ]
    weighted_stds = [
        float(paper["std"])
        for paper in papers
        if isinstance(paper.get("std"), (int, float))
    ]
    metadata = data.get("metadata", {})

    return {
        "source": str(TOP50_PROPORTIONAL_PATH.relative_to(ROOT)),
        "metadata": metadata,
        "selection_strategy": "按全量 1920 篇学科占比分配 Top50 配额，在各学科内择优形成专家审阅版。",
        "total": metadata.get("total", len(papers)),
        "score_distribution": numeric_stats(scores),
        "weighted_std_distribution": numeric_stats(weighted_stds),
        "weighted_std_bands": {
            "lte_5": sum(1 for value in weighted_stds if value <= 5),
            "lte_8": sum(1 for value in weighted_stds if value <= 8),
            "gt_8": sum(1 for value in weighted_stds if value > 8),
        },
        "discipline_quotas": data.get("discipline_quotas", {}),
        "discipline_quota_total": sum(
            int(value) for value in data.get("discipline_quotas", {}).values()
        ),
        "journal_counts": data.get("journal_distribution", {}),
        "year_counts": data.get("year_distribution", {}),
        "category_counts": dict(Counter(paper.get("category", "") for paper in papers)),
        "source_distribution": dict(Counter(paper.get("source", "") for paper in papers)),
        "papers": papers,
    }


def id_integrity(
    metadata: dict[int, dict[str, str]],
    ranking_by_pid: dict[int, dict[str, Any]],
    round2: dict[int, dict[str, Any]],
    top101_ids: set[int],
    top50_ids: set[int],
) -> dict[str, Any]:
    metadata_ids = set(metadata)
    ranking_ids = set(ranking_by_pid)
    round2_ids = set(round2)
    all_ids = metadata_ids | ranking_ids | round2_ids
    numeric_missing = []
    if all_ids:
        numeric_missing = [
            pid
            for pid in range(min(all_ids), max(all_ids) + 1)
            if pid not in all_ids
        ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "join_rule": "必须用 results/merged-metadata.csv 的 编号 字段与 pid 连接，不得使用 CSV 行号或列表下标。",
        "counts": {
            "metadata": len(metadata_ids),
            "unified_rankings": len(ranking_ids),
            "round2": len(round2_ids),
            "top101_e2_candidates": len(top101_ids),
            "top50_proportional": len(top50_ids),
        },
        "id_sets_equal": {
            "metadata_vs_unified_rankings": metadata_ids == ranking_ids,
            "metadata_vs_round2": metadata_ids == round2_ids,
            "unified_rankings_vs_round2": ranking_ids == round2_ids,
        },
        "id_range": {
            "min": min(all_ids) if all_ids else None,
            "max": max(all_ids) if all_ids else None,
            "missing_numeric_ids": numeric_missing,
        },
        "missing": {
            "metadata_missing_from_rankings": sorted(ranking_ids - metadata_ids),
            "rankings_missing_from_metadata": sorted(metadata_ids - ranking_ids),
            "metadata_missing_from_round2": sorted(round2_ids - metadata_ids),
            "round2_missing_from_metadata": sorted(metadata_ids - round2_ids),
            "top101_missing_from_rankings": sorted(top101_ids - ranking_ids),
            "top50_missing_from_rankings": sorted(top50_ids - ranking_ids),
        },
    }


def top_threshold_counts(values: list[float]) -> dict[str, int]:
    return {
        "gte_80": sum(1 for value in values if value >= 80),
        "gte_85": sum(1 for value in values if value >= 85),
        "gte_88": sum(1 for value in values if value >= 88),
        "gte_90": sum(1 for value in values if value >= 90),
    }


def dimension_stats(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for dim, name_zh in DIMENSIONS:
        avgs = [
            float(paper["dim_avgs"][dim])
            for paper in rankings
            if isinstance(paper.get("dim_avgs", {}).get(dim), (int, float))
        ]
        stds = [
            float(paper["dim_stds"][dim])
            for paper in rankings
            if isinstance(paper.get("dim_stds", {}).get(dim), (int, float))
        ]
        rows.append(
            {
                "dimension": dim,
                "name_zh": name_zh,
                "score": numeric_stats(avgs),
                "std": numeric_stats(stds),
            }
        )
    return rows


def round2_reliability(round2: dict[int, dict[str, Any]]) -> dict[str, Any]:
    values = list(round2.values())
    round1_avg = [
        float(item["round1_avg_std"])
        for item in values
        if isinstance(item.get("round1_avg_std"), (int, float))
    ]
    round2_avg = [
        float(item["round2_avg_std"])
        for item in values
        if isinstance(item.get("round2_avg_std"), (int, float))
    ]
    improvement = [
        float(item["std_improvement"])
        for item in values
        if isinstance(item.get("std_improvement"), (int, float))
    ]

    total_dimensions = sum(int(item.get("total_dimensions") or 0) for item in values)
    dimensions_converged = sum(
        int(item.get("dimensions_converged") or 0) for item in values
    )

    return {
        "round1_avg_std": numeric_stats(round1_avg),
        "round2_avg_std": numeric_stats(round2_avg),
        "std_improvement": numeric_stats(improvement),
        "round2_avg_std_bands": {
            "lte_5": sum(1 for value in round2_avg if value <= 5),
            "lte_8": sum(1 for value in round2_avg if value <= 8),
            "lte_12": sum(1 for value in round2_avg if value <= 12),
            "gt_12": sum(1 for value in round2_avg if value > 12),
        },
        "full_dimension_convergence_papers": sum(
            1
            for item in values
            if item.get("dimensions_converged") == item.get("total_dimensions")
        ),
        "dimension_convergence": {
            "dimensions_converged": dimensions_converged,
            "total_dimensions": total_dimensions,
            "ratio": rounded(
                dimensions_converged / total_dimensions
                if total_dimensions
                else None
            ),
        },
    }


def build_overview(
    rankings: list[dict[str, Any]],
    ranking_metadata: dict[str, Any],
    metadata: dict[int, dict[str, str]],
    round2: dict[int, dict[str, Any]],
    round1_err: dict[str, Any],
    top_candidates: dict[str, Any],
    top50_proportional: dict[str, Any],
    integrity: dict[str, Any],
) -> dict[str, Any]:
    scores = [
        float(paper["weighted_score"])
        for paper in rankings
        if isinstance(paper.get("weighted_score"), (int, float))
    ]
    weighted_stds = [
        float(paper["weighted_std"])
        for paper in rankings
        if isinstance(paper.get("weighted_std"), (int, float))
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": {
            "metadata": str(METADATA_PATH.relative_to(ROOT)),
            "rankings": str(RANKINGS_PATH.relative_to(ROOT)),
            "top101_ranking": str(TOP101_RANKING_PATH.relative_to(ROOT)),
            "round2_dir": str(ROUND2_DIR.relative_to(ROOT)),
            "round1_err": str(ROUND1_ERR_PATH.relative_to(ROOT)),
            "top50_proportional": str(TOP50_PROPORTIONAL_PATH.relative_to(ROOT)),
        },
        "corpus_counts": {
            "metadata_rows": len(metadata),
            "ranking_papers": len(rankings),
            "round2_files": len(round2),
        },
        "unified_ranking_metadata": ranking_metadata,
        "score_distribution": numeric_stats(scores),
        "weighted_std_distribution": numeric_stats(weighted_stds),
        "top_threshold_counts": top_threshold_counts(scores),
        "source_counts": dict(Counter(paper.get("source", "") for paper in rankings)),
        "e2_override_count": sum(1 for paper in rankings if paper.get("e2_override")),
        "e3_merged_count": sum(1 for paper in rankings if paper.get("e3_merged")),
        "dimension_stats": dimension_stats(rankings),
        "round2_reliability": round2_reliability(round2),
        "round1_process_issues": round1_err.get("summary", {}),
        "top101_e2_candidates": {
            "selection_strategy": top_candidates["selection_strategy"],
            "source": top_candidates["source"],
            "total_candidates": top_candidates["total_candidates"],
            "composition": top_candidates["composition"],
            "score_distribution": top_candidates["score_distribution"],
            "weighted_std_distribution": top_candidates[
                "weighted_std_distribution"
            ],
            "source_distribution": top_candidates["source_distribution"],
            "journal_counts": top_candidates["journal_counts"],
            "year_counts": top_candidates["year_counts"],
            "category_counts": top_candidates["category_counts"],
        },
        "top50_proportional": {
            "selection_strategy": top50_proportional["selection_strategy"],
            "source": top50_proportional["source"],
            "metadata": top50_proportional["metadata"],
            "total": top50_proportional["total"],
            "score_distribution": top50_proportional["score_distribution"],
            "weighted_std_distribution": top50_proportional[
                "weighted_std_distribution"
            ],
            "weighted_std_bands": top50_proportional["weighted_std_bands"],
            "discipline_quotas": top50_proportional["discipline_quotas"],
            "discipline_quota_total": top50_proportional[
                "discipline_quota_total"
            ],
            "journal_counts": top50_proportional["journal_counts"],
            "year_counts": top50_proportional["year_counts"],
            "category_counts": top50_proportional["category_counts"],
            "source_distribution": top50_proportional["source_distribution"],
        },
        "id_integrity": integrity,
    }


def master_rows(
    rankings: list[dict[str, Any]],
    metadata: dict[int, dict[str, str]],
    round2: dict[int, dict[str, Any]],
    round1_categories: dict[int, str],
    top101_candidates: dict[str, Any],
    top50_proportional: dict[str, Any],
) -> list[dict[str, Any]]:
    top101_by_pid = {
        int(paper["pid"]): paper for paper in top101_candidates.get("papers", [])
    }
    top50_by_pid = {
        int(paper["pid"]): paper
        for paper in top50_proportional.get("papers", [])
        if isinstance(paper.get("pid"), int)
    }
    rows = []
    for paper in rankings:
        pid = int(paper["pid"])
        meta = metadata.get(pid, {})
        reliability = round2.get(pid, {})
        row: dict[str, Any] = {
            "pid": pid,
            "rank": paper.get("rank"),
            "title": meta.get("题目", ""),
            "author": meta.get("作者", ""),
            "journal": meta.get("期刊", ""),
            "year": meta.get("年份", ""),
            "category": meta.get("分类", ""),
            "weighted_score": paper.get("weighted_score"),
            "weighted_std": paper.get("weighted_std"),
            "source": paper.get("source", ""),
            "e2_override": paper.get("e2_override", False),
            "e3_merged": ",".join(paper.get("e3_merged", [])),
            "round1_avg_std": reliability.get("round1_avg_std"),
            "round2_avg_std": reliability.get("round2_avg_std"),
            "std_improvement": reliability.get("std_improvement"),
            "round1_max_std": reliability.get("round1_max_std"),
            "round2_max_std": reliability.get("round2_max_std"),
            "dimensions_converged": reliability.get("dimensions_converged"),
            "total_dimensions": reliability.get("total_dimensions"),
            "round1_err_category": round1_categories.get(pid, ""),
            "top30": int((paper.get("rank") or 0) <= 30),
            "top60": int((paper.get("rank") or 0) <= 60),
            "top101_e2_candidate": int(pid in top101_by_pid),
            "top101_rank": top101_by_pid.get(pid, {}).get("rank", ""),
            "top101_score": top101_by_pid.get(pid, {}).get("score", ""),
            "top101_weighted_std": top101_by_pid.get(pid, {}).get(
                "weighted_std", ""
            ),
            "top101_source": top101_by_pid.get(pid, {}).get("source", ""),
            "top101_reason": top101_by_pid.get(pid, {}).get("reason", ""),
            "top50_proportional": int(pid in top50_by_pid),
            "top50_rank": top50_by_pid.get(pid, {}).get("rank", ""),
            "top50_score": top50_by_pid.get(pid, {}).get("score", ""),
            "top50_weighted_std": top50_by_pid.get(pid, {}).get("std", ""),
        }
        for dim, _name_zh in DIMENSIONS:
            row[f"{dim}_avg"] = paper.get("dim_avgs", {}).get(dim)
            row[f"{dim}_std"] = paper.get("dim_stds", {}).get(dim)
            row[f"{dim}_method"] = paper.get("dim_methods", {}).get(dim)
        rows.append(row)
    return rows


def write_master_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "pid",
        "rank",
        "title",
        "author",
        "journal",
        "year",
        "category",
        "weighted_score",
        "weighted_std",
        "source",
        "e2_override",
        "e3_merged",
        "round1_avg_std",
        "round2_avg_std",
        "std_improvement",
        "round1_max_std",
        "round2_max_std",
        "dimensions_converged",
        "total_dimensions",
        "round1_err_category",
        "top30",
        "top60",
        "top101_e2_candidate",
        "top101_rank",
        "top101_score",
        "top101_weighted_std",
        "top101_source",
        "top101_reason",
        "top50_proportional",
        "top50_rank",
        "top50_score",
        "top50_weighted_std",
    ]
    for dim, _name_zh in DIMENSIONS:
        fieldnames.extend([f"{dim}_avg", f"{dim}_std", f"{dim}_method"])

    with MASTER_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def grouped_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for group_type, field in [
            ("year", "year"),
            ("journal", "journal"),
            ("category", "category"),
        ]:
            group_value = str(row.get(field) or "").strip()
            if group_value:
                groups[(group_type, group_value)].append(row)

    output = []
    for (group_type, group_name), items in sorted(groups.items()):
        scores = [float(item["weighted_score"]) for item in items]
        weighted_stds = [
            float(item["weighted_std"])
            for item in items
            if item.get("weighted_std") not in ("", None)
        ]
        round2_avg_stds = [
            float(item["round2_avg_std"])
            for item in items
            if item.get("round2_avg_std") not in ("", None)
        ]
        top_item = max(items, key=lambda item: float(item["weighted_score"]))
        dimensions_total = sum(int(item.get("total_dimensions") or 0) for item in items)
        dimensions_converged = sum(
            int(item.get("dimensions_converged") or 0) for item in items
        )

        output.append(
            {
                "group_type": group_type,
                "group_name": group_name,
                "n": len(items),
                "score_mean": rounded(statistics.mean(scores)),
                "score_median": rounded(statistics.median(scores)),
                "score_p25": rounded(percentile(scores, 0.25)),
                "score_p75": rounded(percentile(scores, 0.75)),
                "score_min": rounded(min(scores)),
                "score_max": rounded(max(scores)),
                "top_pid": top_item["pid"],
                "top_title": top_item["title"],
                "top_score": top_item["weighted_score"],
                "top30_count": sum(int(item["top30"]) for item in items),
                "top60_count": sum(int(item["top60"]) for item in items),
                "top101_e2_candidate_count": sum(
                    int(item["top101_e2_candidate"]) for item in items
                ),
                "top50_proportional_count": sum(
                    int(item["top50_proportional"]) for item in items
                ),
                "weighted_std_mean": rounded(
                    statistics.mean(weighted_stds) if weighted_stds else None
                ),
                "round2_avg_std_mean": rounded(
                    statistics.mean(round2_avg_stds) if round2_avg_stds else None
                ),
                "dimensions_converged": dimensions_converged,
                "total_dimensions": dimensions_total,
                "dimension_convergence_ratio": rounded(
                    dimensions_converged / dimensions_total
                    if dimensions_total
                    else None
                ),
            }
        )
    return output


def write_group_stats_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "group_type",
        "group_name",
        "n",
        "score_mean",
        "score_median",
        "score_p25",
        "score_p75",
        "score_min",
        "score_max",
        "top_pid",
        "top_title",
        "top_score",
        "top30_count",
        "top60_count",
        "top101_e2_candidate_count",
        "top50_proportional_count",
        "weighted_std_mean",
        "round2_avg_std_mean",
        "dimensions_converged",
        "total_dimensions",
        "dimension_convergence_ratio",
    ]
    with GROUP_STATS_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    metadata = load_metadata()
    rankings, ranking_by_pid, ranking_metadata = load_rankings()
    round2 = load_round2()
    round1_categories, round1_err = load_round1_error_categories()

    top_candidates = load_top101_candidates(metadata)
    top50_proportional = load_top50_proportional()
    top101_ids = {int(paper["pid"]) for paper in top_candidates["papers"]}
    top50_ids = {
        int(paper["pid"])
        for paper in top50_proportional.get("papers", [])
        if isinstance(paper.get("pid"), int)
    }
    integrity = id_integrity(
        metadata,
        ranking_by_pid,
        round2,
        top101_ids,
        top50_ids,
    )
    overview = build_overview(
        rankings,
        ranking_metadata,
        metadata,
        round2,
        round1_err,
        top_candidates,
        top50_proportional,
        integrity,
    )
    rows = master_rows(
        rankings,
        metadata,
        round2,
        round1_categories,
        top_candidates,
        top50_proportional,
    )
    group_rows = grouped_stats(rows)

    write_json(TOP_CANDIDATES_OUT, top_candidates)
    write_json(ID_INTEGRITY_OUT, integrity)
    write_json(OVERVIEW_OUT, overview)
    write_json(
        RANKINGS_PATH,
        {
            "metadata": ranking_metadata,
            "all_papers": rankings,
            "top30": rankings[:30],
            "top60": rankings[:60],
        },
    )
    write_master_csv(rows)
    write_group_stats_csv(group_rows)

    print(f"Wrote {OVERVIEW_OUT.relative_to(ROOT)}")
    print(f"Wrote {MASTER_OUT.relative_to(ROOT)} ({len(rows)} rows)")
    print(f"Wrote {GROUP_STATS_OUT.relative_to(ROOT)} ({len(group_rows)} rows)")
    print(f"Wrote {TOP_CANDIDATES_OUT.relative_to(ROOT)}")
    print(f"Wrote {ID_INTEGRITY_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
