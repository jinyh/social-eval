#!/usr/bin/env python3
"""从现有逐篇结果重建数据集中心目录、摘要、排名和审计清单。"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any

import yaml

from src.knowledge.registry import load_scoring_protocol
from src.reporting.scoring import calculate_weighted_total

DIMENSIONS = {
    "problem_originality": "研究创新性",
    "literature_insight": "现状洞察度",
    "analytical_framework": "理论建构力",
    "logical_coherence": "逻辑连贯性",
    "conclusion_consensus": "学术共识度",
    "forward_extension": "前瞻延展性",
}
AXES = {
    "object_belonging": "对象归属度",
    "material_belonging": "材料归属度",
    "category_autonomy": "范畴自主度",
    "explanatory_orientation": "解释目标归属度",
    "system_mappability": "体系映射度",
}
DUPLICATE_GROUPS = ((231, 232), (264, 265), (1255, 1256), (1551, 1552))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def paper_id(path: Path) -> int:
    return int(path.stem.removeprefix("paper-"))


def score_rows(per_paper: Path, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(per_paper.glob("paper-*.json"), key=paper_id):
        data = read_json(path)
        pid = paper_id(path)
        row: dict[str, Any] = {"paper_id": pid, "paper": data.get("paper", "")}
        dimension_means: dict[str, float] = {}
        for key, label in DIMENSIONS.items():
            payload = data.get("dimensions", {}).get(key, {})
            scores = payload.get("round2_scores") or payload.get("round1_scores") or {}
            values = [float(value) for value in scores.values()]
            mean = statistics.mean(values) if values else 0.0
            std = statistics.pstdev(values) if len(values) > 1 else 0.0
            dimension_means[key] = mean
            row[label] = round(mean, 2)
            row[f"{label}_std"] = round(std, 2)
        row["ccb_score"] = calculate_weighted_total(dimension_means, protocol)
        overall = data.get("overall", {})
        row["round1_avg_std"] = overall.get("round1_avg_std")
        row["round2_avg_std"] = overall.get("round2_avg_std")
        rows.append(row)
    return rows


def five_axis_rows(per_paper: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(per_paper.glob("paper-*.json"), key=paper_id):
        data = read_json(path)
        final = data.get("final", {})
        pid = paper_id(path)
        row: dict[str, Any] = {"paper_id": pid, "paper": data.get("paper", "")}
        for key, label in AXES.items():
            row[label] = final.get("axis_scores", {}).get(key, {}).get("score", 0)
        row.update(
            {
                "五轴总分": final.get("total_score", 0),
                "强度": final.get("strength", "absent"),
                "一致性": final.get("agreement_level", "none"),
                "需复核": final.get("review_required", False),
                "R2模式": data.get("round2_mode", ""),
            }
        )
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def metadata_rows(source: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    duplicate_by_pid: dict[int, tuple[int, int]] = {
        pid: group for group in DUPLICATE_GROUPS for pid in group
    }
    enriched: list[dict[str, str]] = []
    deduplicated: list[dict[str, str]] = []
    for row in rows:
        pid = int(row["编号"])
        group = duplicate_by_pid.get(pid)
        item = dict(row)
        item["duplicate_group"] = "-".join(map(str, group)) if group else ""
        item["canonical_pid"] = str(group[0] if group else pid)
        item["analysis_included"] = "yes" if not group or pid == group[0] else "no"
        enriched.append(item)
        if item["analysis_included"] == "yes":
            deduplicated.append(item)
    return enriched, deduplicated


def r1_audit(source_root: Path) -> dict[str, Any]:
    base = source_root / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55"
    r1_paths = list((base / "audit/round1-standalone").glob("paper-*.json"))
    r1_paths.extend((base / "audit/round1-errors").glob("*/paper-*.json"))
    r1_by_id = {paper_id(path): path for path in r1_paths}
    exact: list[int] = []
    mismatch: list[int] = []
    missing: list[int] = []
    r2_paths = sorted((base / "per-paper").glob("paper-*.json"), key=paper_id)
    for r2_path in r2_paths:
        pid = paper_id(r2_path)
        r1_path = r1_by_id.get(pid)
        if not r1_path:
            missing.append(pid)
            continue
        standalone = read_json(r1_path).get("dimensions", {})
        embedded = read_json(r2_path).get("dimensions", {})
        left = {
            key: value.get("model_scores", value.get("round1_scores", {}))
            for key, value in standalone.items()
        }
        right = {key: value.get("round1_scores", {}) for key, value in embedded.items()}
        (exact if left == right else mismatch).append(pid)
    return {
        "round2_total": len(r2_paths),
        "standalone_round1_total": len(r1_by_id),
        "exact_matches": len(exact),
        "mismatches": len(mismatch),
        "missing": len(missing),
        "mismatch_paper_ids": mismatch,
        "missing_paper_ids": missing,
        "decision": "记录差异，不重跑；R1 独立文件与 R2 内嵌 R1 均保留作历史审计。",
    }


def dataset_manifest(
    dataset: str,
    metadata: str,
    six_count: int,
    five_count: int,
    six_source: str,
    five_source: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "status": "active",
        "metadata": metadata,
        "six_dimension": {
            "run_id": "phase2-r2-v2.55",
            "count": six_count,
            "summary": "six-dimension/phase2-r2-v2.55/summary.csv",
            "per_paper": "six-dimension/phase2-r2-v2.55/per-paper/",
            "storage": "local-untracked",
            "migrated_from": six_source,
        },
        "five_axis": {
            "run_id": "position-v0.2",
            "count": five_count,
            "summary": "five-axis/position-v0.2/summary.csv",
            "per_paper": "five-axis/position-v0.2/per-paper/",
            "storage": "local-untracked",
            "migrated_from": five_source,
        },
    }


def build_rankings(
    source_root: Path, output_root: Path, protocol: dict[str, Any]
) -> None:
    e1_rows = score_rows(
        source_root
        / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper",
        protocol,
    )
    e1_by_pid = {int(row["paper_id"]): row for row in e1_rows}
    e2_data = read_json(source_root / "results/rankings/e2-ccb-v5/ranking.json")
    e2_by_pid = {int(row["pid"]): row for row in e2_data["papers"]}
    metadata, _ = metadata_rows(
        source_root / "results/datasets/three-journals/metadata.csv"
    )
    meta_by_pid = {int(row["编号"]): row for row in metadata}
    papers: list[dict[str, Any]] = []
    for pid in sorted(meta_by_pid):
        if pid in e2_by_pid:
            e2 = e2_by_pid[pid]
            dimensions = {
                key: payload["pooled_avg"] for key, payload in e2["dimensions"].items()
            }
            score = calculate_weighted_total(dimensions, protocol)
            source = "E1+E2"
        else:
            e1 = e1_by_pid[pid]
            dimensions = {key: e1[label] for key, label in DIMENSIONS.items()}
            score = e1["ccb_score"]
            source = "E1"
        papers.append(
            {
                "pid": pid,
                "source": source,
                "ccb_score": score,
                "dimensions": dimensions,
                "metadata": meta_by_pid[pid],
            }
        )
    papers.sort(key=lambda row: (-float(row["ccb_score"]), int(row["pid"])))
    for rank, row in enumerate(papers, 1):
        row["rank"] = rank
    source_distribution = {
        source: sum(row["source"] == source for row in papers)
        for source in ("E1", "E1+E2")
    }
    canonical = {
        "metadata": {
            "version": "all-papers-ccb-v1",
            "total": len(papers),
            "source_distribution": source_distribution,
            "scoring": "core-ceiling-bonus-v0.8",
        },
        "papers": papers,
    }
    write_json(
        output_root / "results/rankings/all-papers-ccb-v1/ranking.json", canonical
    )
    write_csv(
        output_root / "results/rankings/all-papers-ccb-v1/summary.csv",
        [
            {
                "rank": row["rank"],
                "pid": row["pid"],
                "source": row["source"],
                "ccb_score": row["ccb_score"],
                "title": row["metadata"].get("题目", ""),
            }
            for row in papers
        ],
    )
    duplicate_secondaries = {group[1] for group in DUPLICATE_GROUPS}
    analysis = [row for row in papers if row["pid"] not in duplicate_secondaries]
    for rank, row in enumerate(analysis, 1):
        row = dict(row)
        row["analysis_rank"] = rank
        analysis[rank - 1] = row
    write_json(
        output_root / "results/rankings/all-papers-ccb-v1/ranking-deduplicated.json",
        {
            "metadata": {
                "total": len(analysis),
                "excluded_duplicate_pids": sorted(duplicate_secondaries),
                "preserves_historical_pid_view": True,
            },
            "papers": analysis,
        },
    )
    write_json(output_root / "results/rankings/e2-ccb-v5/ranking.json", e2_data)
    write_json(
        output_root / "results/rankings/e2-ccb-v5/pool.json",
        read_json(source_root / "results/rankings/e2-ccb-v5/pool.json"),
    )


def build(source_root: Path, output_root: Path) -> None:
    protocol = load_scoring_protocol()
    datasets = {
        "three-journals": {
            "six": source_root
            / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper",
            "five": source_root
            / "results/datasets/three-journals/five-axis/position-v0.2/per-paper",
            "metadata": "metadata.csv",
            "metadata_source": "results/datasets/three-journals/metadata.csv",
            "six_migrated_from": "results/fullevaluation/round2",
            "five_migrated_from": "results/fullpaper-position-assessment-stage0/merged",
        },
        "jiaodafaxue": {
            "six": source_root
            / "results/datasets/jiaodafaxue/six-dimension/phase2-r2-v2.55/per-paper",
            "five": source_root
            / "results/datasets/jiaodafaxue/five-axis/position-v0.2/per-paper",
            "metadata": "metadata.json",
            "metadata_source": "results/datasets/jiaodafaxue/metadata.json",
            "six_migrated_from": "results/jiaodafaxue-evaluation/round2",
            "five_migrated_from": "results/jiaodafaxue-position-assessment/merged",
        },
        "xueshuyuekan": {
            "six": source_root
            / "results/datasets/xueshuyuekan/six-dimension/phase2-r2-v2.55/per-paper",
            "five": source_root
            / "results/datasets/xueshuyuekan/five-axis/position-v0.2/per-paper",
            "metadata": "metadata.json",
            "metadata_source": "由逐篇结果路径生成",
            "six_migrated_from": "results/xueshuyuekan/round2",
            "five_migrated_from": "results/xueshuyuekan-position-assessment/merged",
        },
    }
    for name, spec in datasets.items():
        base = output_root / "results/datasets" / name
        six_rows = score_rows(spec["six"], protocol)
        five_rows = five_axis_rows(spec["five"])
        write_csv(base / "six-dimension/phase2-r2-v2.55/summary.csv", six_rows)
        write_csv(base / "five-axis/position-v0.2/summary.csv", five_rows)
        six_manifest = {
            "run_id": "phase2-r2-v2.55",
            "framework_role": "six_dimension_cross_review",
            "framework": "configs/frameworks/law-v2.55-cross-review.yaml",
            "scoring_protocol": "configs/scoring/core-ceiling-bonus-v0.8.yaml",
            "paper_count": len(six_rows),
            "summary": "summary.csv",
            "per_paper": "per-paper/",
        }
        if name != "xueshuyuekan":
            six_manifest["audit"] = "audit/"
        write_yaml(
            base / "six-dimension/phase2-r2-v2.55/manifest.yaml",
            six_manifest,
        )
        write_yaml(
            base / "five-axis/position-v0.2/manifest.yaml",
            {
                "run_id": "position-v0.2",
                "framework_role": "five_axis_default",
                "framework": "configs/frameworks/law-position-v0.2.yaml",
                "paper_count": len(five_rows),
                "summary": "summary.csv",
                "per_paper": "per-paper/",
            },
        )
        if name == "three-journals":
            full, dedup = metadata_rows(
                source_root / "results/datasets/three-journals/metadata.csv"
            )
            write_csv(base / "metadata.csv", full)
            write_csv(base / "metadata-deduplicated.csv", dedup)
        elif name == "jiaodafaxue":
            write_json(
                base / "metadata.json",
                read_json(source_root / "results/datasets/jiaodafaxue/metadata.json"),
            )
        else:
            write_json(
                base / "metadata.json",
                {
                    "total": len(six_rows),
                    "papers": [
                        {"id": row["paper_id"], "path": row["paper"]}
                        for row in six_rows
                    ],
                },
            )
        write_yaml(
            base / "manifest.yaml",
            dataset_manifest(
                name,
                spec["metadata"],
                len(six_rows),
                len(five_rows),
                spec["six_migrated_from"],
                spec["five_migrated_from"],
            ),
        )
    audit = r1_audit(source_root)
    write_json(output_root / "results/reports/current/r1-linkage-audit.json", audit)
    build_rankings(source_root, output_root, protocol)
    write_yaml(
        output_root / "results/catalog.yaml",
        {
            "version": 1,
            "active_datasets": list(datasets),
            "rankings": ["all-papers-ccb-v1", "e2-ccb-v5"],
            "reports": {"current": "reports/current/"},
            "storage_policy": {
                "tracked": "metadata, summaries, rankings, manifests, integrity reports",
                "local_untracked": "per-paper AI outputs, raw corpora, execution logs",
                "cold_archive": "../SocialEval-archive/2026-07-16-deep-clean/",
            },
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("."))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build(args.source_root.resolve(), args.output_root.resolve())
