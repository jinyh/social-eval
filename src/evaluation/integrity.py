"""框架、代码入口与活动结果的一一对应审计。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from src.knowledge.loader import load_framework
from src.knowledge.registry import (
    assert_embedded_scoring_protocols_match,
    load_position_framework,
    load_registry,
    load_review_protocol,
    load_scoring_protocol,
)


def _csv_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate_e2_pool_records(records: list[dict[str, Any]]) -> list[str]:
    """检查 E2 当前池的两项硬门槛。"""

    errors: list[str] = []
    for record in records:
        pid = int(record["id"])
        e1 = float(record.get("e1_score", 0))
        axis5 = float(record.get("axis5_total", 0))
        if e1 < 80:
            errors.append(f"paper-{pid}: E1 CCB {e1} < 80")
        if axis5 < 9:
            errors.append(f"paper-{pid}: 五轴 {axis5} < 9")
    return errors


def audit_active_results(project_root: Path) -> dict[str, Any]:
    """只读审计注册框架、数据集摘要、排名和可用逐篇结果。"""

    root = project_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    registry_path = root / "configs/frameworks/registry.yaml"
    registry = load_registry(registry_path)
    frameworks: dict[str, dict[str, Any]] = {}
    for role, entry in registry["frameworks"].items():
        path = (registry_path.parent / entry["path"]).resolve()
        try:
            if role == "five_axis_default":
                payload = load_position_framework(role, registry_path)
                version = payload["metadata"]["version"]
                status = payload["metadata"]["status"]
            else:
                framework = load_framework(path)
                version = framework.version
                status = framework.metadata.status if framework.metadata else ""
            frameworks[role] = {
                "path": str(path.relative_to(root)),
                "version": version,
                "status": status,
                "valid": True,
            }
            if status != entry.get("status"):
                errors.append(
                    f"{role}: registry status={entry.get('status')} != metadata status={status}"
                )
        except Exception as exc:  # noqa: BLE001 - 审计必须汇总所有配置错误
            frameworks[role] = {"path": str(path), "valid": False, "error": str(exc)}
            errors.append(f"{role}: {exc}")
    mismatches = assert_embedded_scoring_protocols_match(registry_path)
    if mismatches:
        errors.append(f"内嵌 CCB 与真源不一致: {mismatches}")
    load_scoring_protocol(registry_path=registry_path)
    review = load_review_protocol(registry_path=registry_path)

    catalog = yaml.safe_load(
        (root / "results/catalog.yaml").read_text(encoding="utf-8")
    )
    datasets: dict[str, Any] = {}
    for dataset in catalog["active_datasets"]:
        base = root / "results/datasets" / dataset
        manifest = yaml.safe_load((base / "manifest.yaml").read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        for family in ("six_dimension", "five_axis"):
            summary = base / manifest[family]["summary"]
            actual = _csv_count(summary)
            expected = int(manifest[family]["count"])
            counts[family] = actual
            if actual != expected:
                errors.append(f"{dataset}.{family}: summary={actual} manifest={expected}")
        datasets[dataset] = counts

    pool = json.loads(
        (root / "results/rankings/e2-ccb-v5/pool.json").read_text(encoding="utf-8")
    )
    ranking = json.loads(
        (root / "results/rankings/e2-ccb-v5/ranking.json").read_text(encoding="utf-8")
    )
    errors.extend(validate_e2_pool_records(pool))
    pool_ids = {int(row["id"]) for row in pool}
    ranking_ids = {int(row["pid"]) for row in ranking["papers"]}
    if pool_ids != ranking_ids:
        errors.append("E2 pool 与 ranking 的 Paper ID 集合不一致")
    for paper in ranking["papers"]:
        if len(paper.get("dimensions", {})) != 6:
            errors.append(f"paper-{paper['pid']}: E2 ranking 不是六维")
            continue
        for key, dimension in paper["dimensions"].items():
            if dimension.get("pooled_n") != 8:
                errors.append(f"paper-{paper['pid']}:{key}: pooled_n != 8")

    per_paper_counts: dict[str, int] = {}
    for dataset, expected in datasets.items():
        for family, count in expected.items():
            run = "phase2-r2-v2.55" if family == "six_dimension" else "position-v0.2"
            folder = family.replace("_", "-")
            per_paper = root / "results/datasets" / dataset / folder / run / "per-paper"
            actual = len(list(per_paper.glob("paper-*.json")))
            per_paper_counts[f"{dataset}.{family}"] = actual
            if per_paper.exists() and actual != count:
                errors.append(
                    f"{dataset}.{family}: per-paper={actual} summary={count}"
                )
            elif not per_paper.exists():
                warnings.append(f"{dataset}.{family}: 本机无逐篇目录，仅校验追踪摘要")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "frameworks": frameworks,
        "review_protocol": {
            "version": review["metadata"]["version"],
            "unresolved_disagreement": review["unresolved_disagreement"],
        },
        "datasets": datasets,
        "per_paper_counts": per_paper_counts,
        "e2": {
            "pool_count": len(pool),
            "ranking_count": len(ranking["papers"]),
        },
    }
