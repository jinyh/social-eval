"""权威结果路径注册表与写入边界检查。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from src.evaluation.repair.models import RepairTarget


def _summary_ids(summary_path: Path) -> tuple[int, ...]:
    if not summary_path.exists():
        return ()
    with summary_path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(
            sorted(
                int(row["paper_id"])
                for row in csv.DictReader(handle)
                if row.get("paper_id")
            )
        )


def _pool_ids(pool_path: Path) -> tuple[int, ...]:
    if not pool_path.exists():
        return ()
    payload = json.loads(pool_path.read_text(encoding="utf-8"))
    return tuple(sorted(int(item["id"]) for item in payload))


def _six_dimension_keys(root: Path) -> tuple[str, ...]:
    path = root / "configs/frameworks/law-v2.55-cross-review.yaml"
    if not path.exists():
        return ()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(str(item["key"]) for item in payload.get("dimensions", []))


def target_registry(project_root: Path) -> dict[str, RepairTarget]:
    """构建以 ``project_root`` 为基准的权威逐篇目录注册表。"""

    root = project_root.resolve()
    datasets = root / "results" / "datasets"
    six_dimensions = _six_dimension_keys(root)
    targets: dict[str, RepairTarget] = {}
    for dataset in ("three-journals", "jiaodafaxue", "xueshuyuekan"):
        six_key = f"{dataset}-six"
        targets[six_key] = RepairTarget(
            key=six_key,
            dataset=dataset,
            family="six_dimension",
            per_paper_dir=(
                datasets
                / dataset
                / "six-dimension"
                / "phase2-r2-v2.55"
                / "per-paper"
            ),
            expected_dimensions=six_dimensions,
            expected_paper_ids=_summary_ids(
                datasets
                / dataset
                / "six-dimension"
                / "phase2-r2-v2.55"
                / "summary.csv"
            ),
        )
        five_key = f"{dataset}-five"
        targets[five_key] = RepairTarget(
            key=five_key,
            dataset=dataset,
            family="five_axis",
            per_paper_dir=(
                datasets / dataset / "five-axis" / "position-v0.2" / "per-paper"
            ),
            expected_paper_ids=_summary_ids(
                datasets
                / dataset
                / "five-axis"
                / "position-v0.2"
                / "summary.csv"
            ),
        )

    e2_base = root / "results" / "rankings" / "e2-ccb-v5" / "per-paper"
    e2_ids = _pool_ids(root / "results/rankings/e2-ccb-v5/pool.json")
    for round_number in (1, 2):
        key = f"e2-r{round_number}"
        targets[key] = RepairTarget(
            key=key,
            dataset="three-journals",
            family="e2",
            per_paper_dir=e2_base / f"round{round_number}",
            round_number=round_number,
            expected_dimensions=six_dimensions,
            expected_paper_ids=e2_ids,
        )
    return targets


def ensure_allowed_path(candidate: Path, allowed_roots: list[Path]) -> Path:
    """解析并验证写入路径位于至少一个允许目录内。"""

    resolved = candidate.resolve()
    roots = [root.resolve() for root in allowed_roots]
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise ValueError(f"路径不在允许写入范围：{resolved}")
    return resolved
