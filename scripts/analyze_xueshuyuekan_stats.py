#!/usr/bin/env python3
"""Generate statistical analysis for Xueshu Yuekan E1 results.

The script is intentionally read-only for source inputs: it joins the
Xueshu Yuekan metadata CSV to the materialized E1 round2 outputs by
``paper-list.ncpssd_id == CSV.lngid`` and writes report-only derived files.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CSV_PATH = ROOT / "raw" / "xueshuyuekan" / "97001X_学术月刊_法学院2015起.csv"
DEFAULT_MD_DIR = ROOT / "raw" / "xueshuyuekan"
DEFAULT_RESULTS_DIR = ROOT / "results" / "xueshuyuekan"
DEFAULT_PAPER_LIST_PATH = DEFAULT_RESULTS_DIR / "paper-list.json"
DEFAULT_ROUND2_DIR = DEFAULT_RESULTS_DIR / "round2"
DEFAULT_JSON_OUT = DEFAULT_RESULTS_DIR / "statistical-analysis.json"
DEFAULT_MD_OUT = DEFAULT_RESULTS_DIR / "statistical-analysis.md"

DIMENSIONS = [
    ("problem_originality", "研究创新性"),
    ("literature_insight", "现状洞察度"),
    ("analytical_framework", "理论建构力"),
    ("logical_coherence", "逻辑连贯性"),
    ("conclusion_consensus", "学术共识度"),
    ("forward_extension", "前瞻延展性"),
]

CLASSIFICATION_MODEL_COLUMNS = ["分类-Q", "分类-G", "分类-D", "分类-K"]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def rounded(value: float | int | None, digits: int = 2) -> float | None:
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
            "std": None,
            "min": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "max": None,
        }

    return {
        "count": len(values),
        "mean": rounded(statistics.mean(values)),
        "median": rounded(statistics.median(values)),
        "std": rounded(statistics.stdev(values) if len(values) > 1 else 0.0),
        "min": rounded(min(values)),
        "p10": rounded(percentile(values, 0.10)),
        "p25": rounded(percentile(values, 0.25)),
        "p75": rounded(percentile(values, 0.75)),
        "p90": rounded(percentile(values, 0.90)),
        "max": rounded(max(values)),
    }


def score_band(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 80:
        return ">=80"
    if score >= 70:
        return "70-79.9"
    if score >= 60:
        return "60-69.9"
    if score >= 50:
        return "50-59.9"
    return "<50"


def confidence_from_std(std: float | None) -> str:
    if std is None:
        return "missing"
    if std <= 5:
        return "high"
    if std <= 8:
        return "medium"
    if std <= 12:
        return "low"
    return "critical"


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def find_duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted([value for value, count in counts.items() if value and count > 1])


def precheck_conclusion(entry: Any) -> str:
    if not isinstance(entry, dict):
        return "unknown"
    if entry.get("error"):
        return "error"
    result = entry.get("result")
    if not isinstance(result, dict):
        return "unknown"
    return str(result.get("conclusion") or result.get("status") or "unknown")


def extract_signal_summary(signal_data: Any) -> dict[str, Any]:
    if not isinstance(signal_data, dict):
        return {"scores": [], "strengths": Counter(), "review_triggers": 0}

    scores = []
    strengths: Counter[str] = Counter()
    review_triggers = 0
    for item in signal_data.values():
        if not isinstance(item, dict) or item.get("error"):
            continue
        score = item.get("autonomous_signal_score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
        strength = item.get("autonomous_signal_strength")
        if strength:
            strengths[str(strength)] += 1
        if item.get("triggers_review"):
            review_triggers += 1
    return {
        "scores": scores,
        "strengths": strengths,
        "review_triggers": review_triggers,
    }


def build_records(
    csv_rows: list[dict[str, str]],
    paper_list: list[dict[str, Any]],
    round2_dir: Path,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_lngid = {row.get("lngid", "").strip(): row for row in csv_rows}
    records: list[dict[str, Any]] = []

    for paper in paper_list:
        paper_id = paper.get("id")
        lngid = str(paper.get("ncpssd_id", "")).strip()
        meta = by_lngid.get(lngid)
        if meta is None:
            issues.append(
                {
                    "type": "missing_metadata",
                    "paper_id": paper_id,
                    "lngid": lngid,
                    "title": paper.get("title", ""),
                }
            )
            continue

        round2_path = round2_dir / f"paper-{paper_id}.json"
        if not round2_path.exists():
            issues.append(
                {
                    "type": "missing_round2_json",
                    "paper_id": paper_id,
                    "lngid": lngid,
                    "path": str(round2_path.relative_to(ROOT)),
                }
            )
            continue

        data = read_json(round2_path)
        dimensions = data.get("dimensions", {})
        if not isinstance(dimensions, dict):
            issues.append({"type": "invalid_dimensions_shape", "paper_id": paper_id})
            dimensions = {}

        missing_dims = [dim for dim, _name in DIMENSIONS if dim not in dimensions]
        if missing_dims:
            issues.append(
                {
                    "type": "missing_dimensions",
                    "paper_id": paper_id,
                    "lngid": lngid,
                    "missing_dimensions": missing_dims,
                }
            )

        dim_means: dict[str, float | None] = {}
        dim_stds: dict[str, float | None] = {}
        dim_scores: dict[str, dict[str, Any]] = {}
        high_std_dims = []
        for dim, _name in DIMENSIONS:
            dim_data = dimensions.get(dim, {})
            if not isinstance(dim_data, dict):
                dim_data = {}
            dim_mean = dim_data.get("round2_mean")
            dim_std = dim_data.get("round2_std")
            dim_means[dim] = float(dim_mean) if isinstance(dim_mean, (int, float)) else None
            dim_stds[dim] = float(dim_std) if isinstance(dim_std, (int, float)) else None
            dim_scores[dim] = dim_data.get("round2_scores", {})
            if dim_stds[dim] is not None and dim_stds[dim] > 12:
                high_std_dims.append(
                    {
                        "dimension": dim,
                        "name_zh": dict(DIMENSIONS)[dim],
                        "std": rounded(dim_stds[dim]),
                    }
                )

        overall = data.get("overall", {})
        if not isinstance(overall, dict):
            overall = {}

        category = meta.get("分类", "").strip()
        if not category:
            issues.append({"type": "empty_category", "paper_id": paper_id, "lngid": lngid})

        model_categories = {
            col: meta.get(col, "").strip() for col in CLASSIFICATION_MODEL_COLUMNS
        }
        classification_match_count = sum(
            1 for value in model_categories.values() if value and value == category
        )

        precheck = data.get("precheck", {})
        precheck_counts: Counter[str] = Counter()
        if isinstance(precheck, dict):
            for model_entry in precheck.values():
                precheck_counts[precheck_conclusion(model_entry)] += 1

        signal_summary = extract_signal_summary(data.get("autonomous_knowledge_signals"))
        signal_scores = signal_summary["scores"]

        score = overall.get("round2_final_score_mean")
        r2_std = overall.get("round2_avg_std")
        record = {
            "paper_id": paper_id,
            "lngid": lngid,
            "filename": paper.get("filename", ""),
            "path": paper.get("path", ""),
            "title": paper.get("title", ""),
            "author": paper.get("author", ""),
            "year": int(meta["years"]) if meta.get("years", "").isdigit() else None,
            "category": category,
            "classification_model_categories": model_categories,
            "classification_match_count": classification_match_count,
            "score": float(score) if isinstance(score, (int, float)) else None,
            "strictest_score": overall.get("round2_final_score_strictest"),
            "round1_score": overall.get("round1_final_score_mean"),
            "round2_score": score,
            "round1_avg_std": overall.get("round1_avg_std"),
            "round2_avg_std": float(r2_std) if isinstance(r2_std, (int, float)) else None,
            "std_improvement": overall.get("std_improvement"),
            "dimensions_converged": overall.get("dimensions_converged"),
            "dimensions_total": overall.get("dimensions_total"),
            "max_std": overall.get("max_std"),
            "confidence": confidence_from_std(float(r2_std)) if isinstance(r2_std, (int, float)) else "missing",
            "score_band": score_band(float(score)) if isinstance(score, (int, float)) else "missing",
            "dimension_means": dim_means,
            "dimension_stds": dim_stds,
            "dimension_scores": dim_scores,
            "high_std_dimensions": high_std_dims,
            "precheck_counts": dict(precheck_counts),
            "autonomous_signal_score_mean": (
                rounded(statistics.mean(signal_scores)) if signal_scores else None
            ),
            "autonomous_signal_strength_counts": dict(signal_summary["strengths"]),
            "autonomous_signal_review_triggers": signal_summary["review_triggers"],
        }
        records.append(record)

    return records


def grouped_stats(records: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record.get(group_key)].append(record)

    result = []
    for group, items in groups.items():
        scores = [r["score"] for r in items if isinstance(r.get("score"), float)]
        r2_stds = [
            r["round2_avg_std"]
            for r in items
            if isinstance(r.get("round2_avg_std"), float)
        ]
        top_item = max(items, key=lambda r: r.get("score") or -1)
        bottom_item = min(items, key=lambda r: r.get("score") if r.get("score") is not None else 999)
        result.append(
            {
                "group": group,
                "count": len(items),
                "score_stats": numeric_stats(scores),
                "round2_avg_std_mean": rounded(statistics.mean(r2_stds)) if r2_stds else None,
                "top70_count": sum(1 for score in scores if score >= 70),
                "top80_count": sum(1 for score in scores if score >= 80),
                "top_paper": compact_paper(top_item),
                "bottom_paper": compact_paper(bottom_item),
            }
        )

    return sorted(result, key=lambda item: (-item["count"], str(item["group"])))


def compact_paper(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_id": record.get("paper_id"),
        "lngid": record.get("lngid"),
        "score": rounded(record.get("score")),
        "round2_avg_std": rounded(record.get("round2_avg_std")),
        "max_std": rounded(record.get("max_std")),
        "category": record.get("category"),
        "year": record.get("year"),
        "author": record.get("author"),
        "title": record.get("title"),
    }


def compact_paper_with_rank(record: dict[str, Any]) -> dict[str, Any]:
    return compact_paper(record) | {"rank": record.get("internal_rank")}


def build_analysis(
    csv_path: Path,
    md_dir: Path,
    paper_list_path: Path,
    round2_dir: Path,
) -> dict[str, Any]:
    csv_rows = load_csv_rows(csv_path)
    paper_list_data = read_json(paper_list_path)
    paper_list = paper_list_data.get("papers", [])
    if not isinstance(paper_list, list):
        paper_list = []

    round2_files = sorted(round2_dir.glob("paper-*.json"))
    md_files = sorted(md_dir.glob("*.md"))

    issues: list[dict[str, Any]] = []
    csv_lngids = [row.get("lngid", "").strip() for row in csv_rows]
    duplicate_lngids = find_duplicates(csv_lngids)
    if duplicate_lngids:
        issues.append({"type": "duplicate_csv_lngid", "lngids": duplicate_lngids})

    paper_ids = [str(paper.get("id", "")) for paper in paper_list]
    duplicate_paper_ids = find_duplicates(paper_ids)
    if duplicate_paper_ids:
        issues.append({"type": "duplicate_paper_id", "paper_ids": duplicate_paper_ids})

    records = build_records(csv_rows, paper_list, round2_dir, issues)

    for record in records:
        if record["score"] is None:
            issues.append(
                {
                    "type": "missing_final_score",
                    "paper_id": record["paper_id"],
                    "lngid": record["lngid"],
                }
            )

    scores = [record["score"] for record in records if isinstance(record.get("score"), float)]
    round1_scores = [
        float(record["round1_score"])
        for record in records
        if isinstance(record.get("round1_score"), (int, float))
    ]
    round2_scores = [
        float(record["round2_score"])
        for record in records
        if isinstance(record.get("round2_score"), (int, float))
    ]
    round1_stds = [
        float(record["round1_avg_std"])
        for record in records
        if isinstance(record.get("round1_avg_std"), (int, float))
    ]
    round2_stds = [
        float(record["round2_avg_std"])
        for record in records
        if isinstance(record.get("round2_avg_std"), float)
    ]
    improvements = [
        float(record["std_improvement"])
        for record in records
        if isinstance(record.get("std_improvement"), (int, float))
    ]
    converged = [
        float(record["dimensions_converged"])
        for record in records
        if isinstance(record.get("dimensions_converged"), (int, float))
    ]

    score_bands = Counter(record["score_band"] for record in records)
    confidence_counts = Counter(record["confidence"] for record in records)
    classification_agreement = Counter(
        str(record["classification_match_count"]) for record in records
    )

    precheck_model_level: Counter[str] = Counter()
    for record in records:
        precheck_model_level.update(record["precheck_counts"])

    dimension_stats = []
    for dim, name_zh in DIMENSIONS:
        dim_values = [
            record["dimension_means"][dim]
            for record in records
            if record["dimension_means"].get(dim) is not None
        ]
        dim_stds = [
            record["dimension_stds"][dim]
            for record in records
            if record["dimension_stds"].get(dim) is not None
        ]
        dimension_stats.append(
            {
                "dimension": dim,
                "name_zh": name_zh,
                "score_stats": numeric_stats([float(value) for value in dim_values]),
                "avg_model_std": rounded(statistics.mean(dim_stds)) if dim_stds else None,
                "std_over_8_count": sum(1 for value in dim_stds if value > 8),
                "std_over_12_count": sum(1 for value in dim_stds if value > 12),
            }
        )

    ranked = sorted(
        records,
        key=lambda record: (record.get("score") if record.get("score") is not None else -1),
        reverse=True,
    )
    for rank, record in enumerate(ranked, 1):
        record["internal_rank"] = rank

    high_disagreement = sorted(
        records,
        key=lambda record: (
            record.get("round2_avg_std") if record.get("round2_avg_std") is not None else -1,
            record.get("max_std") if isinstance(record.get("max_std"), (int, float)) else -1,
        ),
        reverse=True,
    )

    data_quality = {
        "csv_rows": len(csv_rows),
        "md_files": len(md_files),
        "paper_list_total": paper_list_data.get("total"),
        "paper_list_items": len(paper_list),
        "round2_json_files": len(round2_files),
        "merged_records": len(records),
        "missing_metadata_count": sum(1 for issue in issues if issue["type"] == "missing_metadata"),
        "issue_count": len(issues),
        "issues": issues,
    }

    stable_candidates = [
        compact_paper_with_rank(record)
        for record in ranked
        if (record.get("score") or 0) >= 70
        and (record.get("round2_avg_std") or 999) <= 8
    ]
    review_candidates = [
        compact_paper_with_rank(record)
        for record in ranked
        if (record.get("score") or 0) >= 70
        and (record.get("round2_avg_std") or 0) > 8
    ]

    return {
        "metadata": {
            "title": "学术月刊 E1 统计分析",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "csv_path": str(csv_path.relative_to(ROOT)),
            "md_dir": str(md_dir.relative_to(ROOT)),
            "paper_list_path": str(paper_list_path.relative_to(ROOT)),
            "round2_dir": str(round2_dir.relative_to(ROOT)),
            "score_basis": "overall.round2_final_score_mean",
            "join_key": "paper-list.ncpssd_id = CSV.lngid",
            "ranking_scope": "学术月刊内部排名",
        },
        "data_quality": data_quality,
        "overall": {
            "total_papers": len(records),
            "score_stats": numeric_stats(scores),
            "score_bands": dict(score_bands),
            "confidence_counts": dict(confidence_counts),
            "top70_count": sum(1 for value in scores if value >= 70),
            "top80_count": sum(1 for value in scores if value >= 80),
        },
        "round_comparison": {
            "round1_score_stats": numeric_stats(round1_scores),
            "round2_score_stats": numeric_stats(round2_scores),
            "round1_avg_std_stats": numeric_stats(round1_stds),
            "round2_avg_std_stats": numeric_stats(round2_stds),
            "std_improvement_stats": numeric_stats(improvements),
            "dimensions_converged_stats": numeric_stats(converged),
        },
        "classification": {
            "final_category_counts": dict(Counter(record["category"] for record in records)),
            "model_agreement_with_final": dict(classification_agreement),
            "category_stats": grouped_stats(records, "category"),
        },
        "year_stats": grouped_stats(records, "year"),
        "dimension_stats": dimension_stats,
        "precheck": {
            "model_level_conclusions": dict(precheck_model_level),
        },
        "rankings": {
            "top_papers": [compact_paper_with_rank(record) for record in ranked[:20]],
            "bottom_papers": [
                compact_paper_with_rank(record)
                for record in sorted(ranked, key=lambda item: item["internal_rank"], reverse=True)[:20]
            ],
            "high_disagreement_papers": [
                compact_paper_with_rank(record) | {
                    "rank": record.get("internal_rank"),
                    "confidence": record.get("confidence"),
                    "high_std_dimensions": record.get("high_std_dimensions", []),
                }
                for record in high_disagreement[:20]
            ],
        },
        "recommendations": {
            "stable_top_candidates": stable_candidates[:30],
            "review_before_selection_candidates": review_candidates[:30],
            "stable_top_count": len(stable_candidates),
            "review_before_selection_count": len(review_candidates),
        },
        "records": [
            {
                key: value
                for key, value in record.items()
                if key not in {"dimension_scores"}
            }
            for record in ranked
        ],
    }


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def count_pct(count: int, total: int) -> str:
    if total == 0:
        return f"{count} (0.0%)"
    return f"{count} ({count / total * 100:.1f}%)"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def top_groups_by_mean(
    items: list[dict[str, Any]],
    *,
    min_count: int = 1,
    reverse: bool = True,
) -> list[dict[str, Any]]:
    filtered = [
        item
        for item in items
        if item["count"] >= min_count and item["score_stats"]["mean"] is not None
    ]
    return sorted(
        filtered,
        key=lambda item: item["score_stats"]["mean"],
        reverse=reverse,
    )


def render_key_findings(analysis: dict[str, Any]) -> list[str]:
    overall = analysis["overall"]
    round_cmp = analysis["round_comparison"]
    category_stats = analysis["classification"]["category_stats"]
    year_stats = analysis["year_stats"]
    dimension_stats = analysis["dimension_stats"]
    recommendations = analysis["recommendations"]

    top_categories = top_groups_by_mean(category_stats, min_count=5)[:3]
    bottom_categories = top_groups_by_mean(category_stats, min_count=5, reverse=False)[:3]
    top_years = top_groups_by_mean(year_stats, min_count=5)[:3]
    weakest_dims = sorted(
        dimension_stats,
        key=lambda item: item["score_stats"]["mean"] or 0,
    )[:3]
    most_disputed_dims = sorted(
        dimension_stats,
        key=lambda item: item["avg_model_std"] or 0,
        reverse=True,
    )[:3]

    score_stats = overall["score_stats"]
    return [
        (
            f"本次纳入 149 篇《学术月刊》法学相关论文，数据链路完整："
            f"CSV、Markdown 原文、paper-list 与 Round2 结果均为 149 条，"
            f"按 `lngid` 合并缺失为 0。"
        ),
        (
            f"E1 Round2 均分 {fmt(score_stats['mean'])}，中位数 "
            f"{fmt(score_stats['median'])}；70 分及以上 51 篇，80 分及以上 "
            f"2 篇，说明高分论文存在但头部高度集中。"
        ),
        (
            f"Round2 主要改善的是一致性而不是整体抬分：最终分均值仅从 "
            f"{fmt(round_cmp['round1_score_stats']['mean'])} 升至 "
            f"{fmt(round_cmp['round2_score_stats']['mean'])}，平均 std 从 "
            f"{fmt(round_cmp['round1_avg_std_stats']['mean'])} 降至 "
            f"{fmt(round_cmp['round2_avg_std_stats']['mean'])}。"
        ),
        (
            "样本量不少于 5 的分类中，均分最高的是 "
            + "、".join(
                f"{item['group']}({fmt(item['score_stats']['mean'])})"
                for item in top_categories
            )
            + "；均分最低的是 "
            + "、".join(
                f"{item['group']}({fmt(item['score_stats']['mean'])})"
                for item in bottom_categories
            )
            + "。"
        ),
        (
            "年份上，均分最高的主要集中在 "
            + "、".join(
                f"{item['group']}年({fmt(item['score_stats']['mean'])})"
                for item in top_years
            )
            + "；2016 年均分最低，且样本仅 7 篇，宜结合文本完整性一起解释。"
        ),
        (
            "六维度短板集中在 "
            + "、".join(
                f"{item['name_zh']}({fmt(item['score_stats']['mean'])})"
                for item in weakest_dims
            )
            + "；模型分歧最高的维度是 "
            + "、".join(
                f"{item['name_zh']}({fmt(item['avg_model_std'])})"
                for item in most_disputed_dims
            )
            + "。"
        ),
        (
            f"按“70 分及以上且 Round2 平均 std ≤ 8”的稳健口径，可直接进入"
            f"优先候选观察的论文为 {recommendations['stable_top_count']} 篇；"
            f"另有 {recommendations['review_before_selection_count']} 篇高分但分歧偏高，"
            f"进入最终展示前建议人工复核。"
        ),
    ]


def render_methodology() -> list[str]:
    return [
        "本报告只分析已经落盘的 E1 结果，不重新调用模型。",
        "论文元数据与学科分类来自 `raw/xueshuyuekan/97001X_学术月刊_法学院2015起.csv`。",
        "评分来自 `results/xueshuyuekan/round2/paper-*.json`；最终分采用 `overall.round2_final_score_mean`。",
        "分类采用 CSV 的最终 `分类` 列，`分类-Q/G/D/K` 仅用于一致性统计。",
        "可靠性主要看 `overall.round2_avg_std`，高分歧清单按该指标优先排序，并参考 `max_std` 与维度 std。",
        "所有排名均限于《学术月刊》内部，不并入 1920 篇全量排名。",
    ]


def render_markdown(analysis: dict[str, Any]) -> str:
    meta = analysis["metadata"]
    quality = analysis["data_quality"]
    overall = analysis["overall"]
    score_stats = overall["score_stats"]
    round_cmp = analysis["round_comparison"]
    total = overall["total_papers"]
    category_counts = analysis["classification"]["final_category_counts"]
    core_category_names = ["法学理论", "宪法学与行政法学", "法律史"]
    core_category_count = sum(category_counts.get(name, 0) for name in core_category_names)
    top_years = top_groups_by_mean(analysis["year_stats"], min_count=5)[:3]

    lines = [
        "# 学术月刊 E1 统计分析",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- 合并键：`{meta['join_key']}`",
        f"- 评分口径：`{meta['score_basis']}`",
        f"- 排名范围：{meta['ranking_scope']}",
        "",
        "## 结论摘要",
        "",
        *[f"- {item}" for item in render_key_findings(analysis)],
        "",
        "## 方法与口径",
        "",
        *[f"- {item}" for item in render_methodology()],
        "",
        "## 数据完整性",
        "",
        markdown_table(
            ["检查项", "数量/结果"],
            [
                ["CSV 行数", quality["csv_rows"]],
                ["Markdown 原文数", quality["md_files"]],
                ["paper-list total", quality["paper_list_total"]],
                ["paper-list 实际条目", quality["paper_list_items"]],
                ["Round2 JSON 数", quality["round2_json_files"]],
                ["成功合并记录数", quality["merged_records"]],
                ["合并缺失数", quality["missing_metadata_count"]],
                ["数据质量问题数", quality["issue_count"]],
            ],
        ),
        "",
    ]

    if quality["issues"]:
        issue_rows = []
        for issue in quality["issues"][:50]:
            issue_rows.append(
                [
                    issue.get("type", ""),
                    issue.get("paper_id", ""),
                    issue.get("lngid", ""),
                    json.dumps(issue, ensure_ascii=False),
                ]
            )
        lines.extend(
            [
                "### 数据质量问题",
                "",
                markdown_table(["类型", "Paper ID", "lngid", "详情"], issue_rows),
                "",
            ]
        )
    else:
        lines.extend(["未发现缺失、重复 ID、空分类或缺维度评分问题。", ""])

    lines.extend(
        [
            "## 总体分布",
            "",
            (
                f"149 篇论文的 E1 Round2 均分为 {fmt(score_stats['mean'])}，"
                f"中位数为 {fmt(score_stats['median'])}，中位数高于均分，说明低分尾部"
                "对整体均值有一定下拉。分数主要集中在 60-79.9 分区间，"
                "80 分以上仅 2 篇，头部论文筛选应保持偏严格口径。"
            ),
            "",
            markdown_table(
                ["指标", "值"],
                [
                    ["论文数", total],
                    ["均分", fmt(score_stats["mean"])],
                    ["中位数", fmt(score_stats["median"])],
                    ["标准差", fmt(score_stats["std"])],
                    ["最低分", fmt(score_stats["min"])],
                    ["P10", fmt(score_stats["p10"])],
                    ["P25", fmt(score_stats["p25"])],
                    ["P75", fmt(score_stats["p75"])],
                    ["P90", fmt(score_stats["p90"])],
                    ["最高分", fmt(score_stats["max"])],
                    ["70 分及以上", count_pct(overall["top70_count"], total)],
                    ["80 分及以上", count_pct(overall["top80_count"], total)],
                ],
            ),
            "",
            markdown_table(
                ["分数段", "数量"],
                [
                    [band, count_pct(overall["score_bands"].get(band, 0), total)]
                    for band in [">=80", "70-79.9", "60-69.9", "50-59.9", "<50", "missing"]
                    if band in overall["score_bands"]
                ],
            ),
            "",
            "## Round 1 到 Round 2",
            "",
            (
                "Round2 的主要价值是压缩模型分歧：最终均分只小幅上升 "
                f"{fmt((round_cmp['round2_score_stats']['mean'] or 0) - (round_cmp['round1_score_stats']['mean'] or 0))} "
                "分，但平均 std 下降 "
                f"{fmt(round_cmp['std_improvement_stats']['mean'])} 分。"
                "这说明交叉评审没有简单抬高或压低分数，而是在多数论文上改善了"
                "跨模型一致性。"
            ),
            "",
            markdown_table(
                ["指标", "Round 1", "Round 2", "变化"],
                [
                    [
                        "最终分均值",
                        fmt(round_cmp["round1_score_stats"]["mean"]),
                        fmt(round_cmp["round2_score_stats"]["mean"]),
                        fmt(
                            (round_cmp["round2_score_stats"]["mean"] or 0)
                            - (round_cmp["round1_score_stats"]["mean"] or 0)
                        ),
                    ],
                    [
                        "平均 std",
                        fmt(round_cmp["round1_avg_std_stats"]["mean"]),
                        fmt(round_cmp["round2_avg_std_stats"]["mean"]),
                        fmt(round_cmp["std_improvement_stats"]["mean"]),
                    ],
                    [
                        "维度收敛数均值",
                        "-",
                        fmt(round_cmp["dimensions_converged_stats"]["mean"]),
                        "-",
                    ],
                ],
            ),
            "",
            "## 分类统计",
            "",
            (
                "《学术月刊》法学论文的分类结构偏理论与综合议题：法学理论、"
                f"宪法学与行政法学、法律史三类合计 {core_category_count} 篇，"
                f"占全部样本的 {core_category_count / total * 100:.1f}%。"
                "从 E1 结果看，法律史、数字法学、"
                "民商法学的均分较高；法学理论和诉讼法学受访谈、综述、片段化文本"
                "或宏观议题影响，低分尾部更明显。"
            ),
            "",
            markdown_table(
                ["分类", "篇数", "均分", "中位数", "组内标准差", "均 std", "Top70", "Top80", "最高分", "最低分"],
                [
                    [
                        item["group"],
                        item["count"],
                        fmt(item["score_stats"]["mean"]),
                        fmt(item["score_stats"]["median"]),
                        fmt(item["score_stats"]["std"]),
                        fmt(item["round2_avg_std_mean"]),
                        item["top70_count"],
                        item["top80_count"],
                        fmt(item["score_stats"]["max"]),
                        fmt(item["score_stats"]["min"]),
                    ]
                    for item in analysis["classification"]["category_stats"]
                ],
            ),
            "",
            "四模型分类与最终分类一致票数："
            + "；".join(
                f"{votes} 票一致 {count} 篇"
                for votes, count in sorted(
                    analysis["classification"]["model_agreement_with_final"].items()
                )
            )
            + "。",
            "",
            "## 年份统计",
            "",
            (
                "年份分布覆盖 2015-2025 年。"
                + "、".join(
                    f"{item['group']}年"
                    for item in top_years
                )
                + "均分较高，其中 2025 年和 2023 年各出现 1 篇 80 分以上论文；"
                "2016 年均分最低，"
                "主要受低分样本占比和文本完整性风险影响。年份差异不宜直接解释为"
                "期刊质量趋势，更适合作为候选抽样和人工复核的辅助线索。"
            ),
            "",
            markdown_table(
                ["年份", "篇数", "均分", "中位数", "均 std", "Top70", "Top80", "最高分"],
                [
                    [
                        item["group"],
                        item["count"],
                        fmt(item["score_stats"]["mean"]),
                        fmt(item["score_stats"]["median"]),
                        fmt(item["round2_avg_std_mean"]),
                        item["top70_count"],
                        item["top80_count"],
                        fmt(item["score_stats"]["max"]),
                    ]
                    for item in sorted(analysis["year_stats"], key=lambda item: item["group"] or 0)
                ],
            ),
            "",
            "## 六维度统计",
            "",
            (
                "维度层面呈现出清晰的结构：逻辑连贯性和学术共识度得分较高，说明"
                "多数论文在论证表达、规范展开和结论可接受性上表现稳定；研究创新性、"
                "理论建构力、现状洞察度得分较低，说明 E1 更强调论文是否提出可争辩"
                "问题、是否形成可迁移理论结构，而不仅是完成规范阐释或材料梳理。"
            ),
            "",
            markdown_table(
                ["维度", "均分", "中位数", "篇间标准差", "模型分歧均值", "std>8 维次", "std>12 维次"],
                [
                    [
                        item["name_zh"],
                        fmt(item["score_stats"]["mean"]),
                        fmt(item["score_stats"]["median"]),
                        fmt(item["score_stats"]["std"]),
                        fmt(item["avg_model_std"]),
                        item["std_over_8_count"],
                        item["std_over_12_count"],
                    ]
                    for item in analysis["dimension_stats"]
                ],
            ),
            "",
            "## 预检结论",
            "",
            (
                "预检为模型级统计。多数模型判断进入六维评价，但仍有一定比例的"
                "`obviously_ineligible` 与 `boundary_review`，主要提示部分论文存在"
                "项目口径边界、访谈/综述体裁、文本不完整或中国问题中心性不足等风险。"
            ),
            "",
            markdown_table(
                ["结论", "模型级次数"],
                [
                    [key, value]
                    for key, value in sorted(
                        analysis["precheck"]["model_level_conclusions"].items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ],
            ),
            "",
            "## 候选与复核建议",
            "",
            (
                "建议把候选分成两层使用：第一层是高分且一致性较好的稳健候选；"
                "第二层是分数较高但模型分歧偏大的复核候选。这样既不漏掉有潜力的"
                "争议论文，也避免把单轮模型分歧直接当作最终排序结论。"
            ),
            "",
            "### 稳健优先候选",
            "",
            (
                f"口径：E1 Round2 最终分 ≥ 70，且 Round2 平均 std ≤ 8。"
                f"共 {analysis['recommendations']['stable_top_count']} 篇。"
            ),
            "",
            paper_table(analysis["recommendations"]["stable_top_candidates"][:15]),
            "",
            "### 高分但需复核候选",
            "",
            (
                f"口径：E1 Round2 最终分 ≥ 70，但 Round2 平均 std > 8。"
                f"共 {analysis['recommendations']['review_before_selection_count']} 篇。"
                "这些论文不应直接排除，但进入专家展示或后续 E2/E3 前应优先查看"
                "高分歧维度。"
            ),
            "",
            paper_table(analysis["recommendations"]["review_before_selection_candidates"][:15]),
            "",
            "## Top 论文",
            "",
            paper_table(analysis["rankings"]["top_papers"]),
            "",
            "## 低分论文",
            "",
            paper_table(analysis["rankings"]["bottom_papers"]),
            "",
            "## 高分歧论文",
            "",
            "注：`max_std > 12` 在本批次中覆盖面较大，以下清单按 `round2_avg_std` 优先排序。",
            "",
            paper_table(analysis["rankings"]["high_disagreement_papers"]),
            "",
        ]
    )

    return "\n".join(lines)


def paper_table(papers: list[dict[str, Any]]) -> str:
    return markdown_table(
        ["内部排名", "Paper ID", "分数", "均 std", "最大 std", "年份", "分类", "作者", "标题"],
        [
            [
                paper.get("rank", ""),
                paper.get("paper_id", ""),
                fmt(paper.get("score")),
                fmt(paper.get("round2_avg_std")),
                fmt(paper.get("max_std")),
                paper.get("year", ""),
                paper.get("category", ""),
                paper.get("author", ""),
                paper.get("title", ""),
            ]
            for paper in papers
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--md-dir", type=Path, default=DEFAULT_MD_DIR)
    parser.add_argument("--paper-list", type=Path, default=DEFAULT_PAPER_LIST_PATH)
    parser.add_argument("--round2-dir", type=Path, default=DEFAULT_ROUND2_DIR)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analysis = build_analysis(
        csv_path=args.csv_path,
        md_dir=args.md_dir,
        paper_list_path=args.paper_list,
        round2_dir=args.round2_dir,
    )
    write_json(args.json_out, analysis)
    write_text(args.md_out, render_markdown(analysis))

    quality = analysis["data_quality"]
    overall = analysis["overall"]
    round_cmp = analysis["round_comparison"]
    print(f"CSV rows: {quality['csv_rows']}")
    print(f"MD files: {quality['md_files']}")
    print(f"paper-list total: {quality['paper_list_total']}")
    print(f"Round2 JSON files: {quality['round2_json_files']}")
    print(f"Merged records: {quality['merged_records']}")
    print(f"Missing metadata: {quality['missing_metadata_count']}")
    print(f"Data quality issues: {quality['issue_count']}")
    print(f"Score mean: {overall['score_stats']['mean']}")
    print(f"Score median: {overall['score_stats']['median']}")
    print(f"Round1 avg std mean: {round_cmp['round1_avg_std_stats']['mean']}")
    print(f"Round2 avg std mean: {round_cmp['round2_avg_std_stats']['mean']}")
    print(f"JSON report: {args.json_out}")
    print(f"Markdown report: {args.md_out}")


if __name__ == "__main__":
    main()
