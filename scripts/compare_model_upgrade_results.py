#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean

MODEL_PAIRS = (
    ("glm-5.1", "glm-5.2"),
    ("qwen3.6-plus", "qwen3.7-max-2026-06-08"),
)


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    )
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _operational_metrics(
    audit_database: Path,
    *,
    model_set_version: str,
) -> list[dict]:
    if not audit_database.exists():
        return []
    connection = sqlite3.connect(audit_database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            WITH units AS (
                SELECT
                    l.task_id,
                    l.dimension_key,
                    l.model_name,
                    MAX(CASE WHEN l.status = 'failed' THEN 1 ELSE 0 END)
                        AS required_retry,
                    MAX(CASE WHEN l.status = 'success' THEN 1 ELSE 0 END)
                        AS eventually_succeeded
                FROM ai_call_logs AS l
                JOIN evaluation_tasks AS t ON t.id = l.task_id
                WHERE
                    t.model_set_version = ?
                    AND l.call_type = 'dimension_score'
                GROUP BY l.task_id, l.dimension_key, l.model_name
            ),
            calls AS (
                SELECT
                    l.model_name,
                    SUM(CASE WHEN l.status = 'failed' THEN 1 ELSE 0 END)
                        AS failed_attempts,
                    SUM(
                        CASE
                            WHEN l.status = 'success'
                                AND l.call_type = 'dimension_score'
                            THEN 1 ELSE 0
                        END
                    ) AS successful_live_calls,
                    SUM(
                        CASE
                            WHEN l.status = 'success'
                                AND l.call_type = 'dimension_score_reuse'
                            THEN 1 ELSE 0
                        END
                    ) AS reused_results,
                    AVG(
                        CASE
                            WHEN l.status = 'success'
                                AND l.call_type = 'dimension_score'
                            THEN l.duration_ms
                        END
                    ) AS mean_success_duration_ms
                FROM ai_call_logs AS l
                JOIN evaluation_tasks AS t ON t.id = l.task_id
                WHERE t.model_set_version = ?
                GROUP BY l.model_name
            )
            SELECT
                c.model_name,
                c.failed_attempts,
                c.successful_live_calls,
                c.reused_results,
                c.mean_success_duration_ms,
                SUM(u.required_retry) AS units_requiring_retry,
                SUM(u.eventually_succeeded) AS completed_live_units
            FROM calls AS c
            LEFT JOIN units AS u ON u.model_name = c.model_name
            GROUP BY c.model_name
            ORDER BY c.model_name
            """,
            (model_set_version, model_set_version),
        ).fetchall()
    finally:
        connection.close()
    metrics = []
    for row in rows:
        completed_units = int(row["completed_live_units"] or 0)
        retry_units = int(row["units_requiring_retry"] or 0)
        metrics.append(
            {
                "candidate_model": row["model_name"],
                "successful_live_calls": int(row["successful_live_calls"] or 0),
                "failed_attempts": int(row["failed_attempts"] or 0),
                "units_requiring_retry": retry_units,
                "unit_retry_rate": (
                    retry_units / completed_units if completed_units else None
                ),
                "reused_results": int(row["reused_results"] or 0),
                "mean_success_duration_ms": (
                    float(row["mean_success_duration_ms"])
                    if row["mean_success_duration_ms"] is not None
                    else None
                ),
            }
        )
    return metrics


def compare(
    manifest_path: Path,
    candidate_dir: Path,
    audit_database: Path | None = None,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"old": [], "new": [], "delta": []}
    )
    completed_papers = []
    missing_papers = []
    model_set_versions: set[str] = set()
    for record in manifest["records"]:
        paper_id = int(record["paper_id"])
        candidate_path = candidate_dir / f"paper-{paper_id}.json"
        if not candidate_path.exists():
            missing_papers.append(paper_id)
            continue
        historical = json.loads(
            Path(record["historical_result_path"]).read_text(encoding="utf-8")
        )
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        if candidate.get("sample_manifest_sha256") != manifest["manifest_sha256"]:
            raise ValueError(f"paper-{paper_id} 使用了不同的样本清单")
        model_set_versions.add(candidate["model_set_version"])
        for dimension_key, historical_dimension in historical["dimensions"].items():
            candidate_dimension = candidate["dimensions"][dimension_key]
            for old_model, new_model in MODEL_PAIRS:
                old_score = float(historical_dimension["round1_scores"][old_model])
                new_score = float(candidate_dimension["scores"][new_model])
                series = values[(dimension_key, new_model)]
                series["old"].append(old_score)
                series["new"].append(new_score)
                series["delta"].append(new_score - old_score)
        completed_papers.append(paper_id)

    metrics = []
    for (dimension_key, model_name), series in sorted(values.items()):
        metrics.append(
            {
                "dimension_key": dimension_key,
                "candidate_model": model_name,
                "sample_count": len(series["delta"]),
                "mean_delta": mean(series["delta"]),
                "mean_absolute_delta": mean(abs(value) for value in series["delta"]),
                "pearson_correlation": _pearson(series["old"], series["new"]),
                "large_shift_rate": (
                    sum(abs(value) > 8 for value in series["delta"])
                    / len(series["delta"])
                ),
            }
        )
    if len(model_set_versions) > 1:
        raise ValueError("候选结果混用了多个模型参数版本")
    model_set_version = next(iter(model_set_versions), None)
    return {
        "sample_manifest_sha256": manifest["manifest_sha256"],
        "candidate_model_parameters": manifest.get("candidate_model_parameters", {}),
        "candidate_model_set_version": model_set_version,
        "completed_paper_count": len(completed_papers),
        "completed_paper_ids": completed_papers,
        "missing_paper_ids": missing_papers,
        "comparison_basis": (
            "同一论文、同一 v2.55 第一轮提示；候选模型生成参数按样本清单冻结。"
        ),
        "notice": "该报告只描述模型升级漂移，不自动批准生产切换。",
        "metrics": metrics,
        "operational_metrics": (
            _operational_metrics(
                audit_database,
                model_set_version=model_set_version,
            )
            if audit_database is not None and model_set_version is not None
            else []
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总两组新旧模型的配对漂移。")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("output/model-upgrade/paired-sample-manifest.json"),
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=Path("output/model-upgrade/candidate-results"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/model-upgrade/comparison-summary.json"),
    )
    parser.add_argument(
        "--audit-database",
        type=Path,
        default=Path("output/model-upgrade/model-calls.sqlite"),
    )
    args = parser.parse_args()
    payload = compare(args.manifest, args.candidate_dir, args.audit_database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"completed={payload['completed_paper_count']} "
        f"missing={len(payload['missing_paper_ids'])} output={args.output}"
    )


if __name__ == "__main__":
    main()
