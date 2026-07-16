"""权威结果路径注册表与写入边界检查。"""

from __future__ import annotations

from pathlib import Path

from src.evaluation.repair.models import RepairTarget


def target_registry(project_root: Path) -> dict[str, RepairTarget]:
    """构建以 ``project_root`` 为基准的权威逐篇目录注册表。"""

    root = project_root.resolve()
    datasets = root / "results" / "datasets"
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
        )
        five_key = f"{dataset}-five"
        targets[five_key] = RepairTarget(
            key=five_key,
            dataset=dataset,
            family="five_axis",
            per_paper_dir=(
                datasets / dataset / "five-axis" / "position-v0.2" / "per-paper"
            ),
        )

    e2_base = root / "results" / "rankings" / "e2-ccb-v5" / "per-paper"
    for round_number in (1, 2):
        key = f"e2-r{round_number}"
        targets[key] = RepairTarget(
            key=key,
            dataset="three-journals",
            family="e2",
            per_paper_dir=e2_base / f"round{round_number}",
            round_number=round_number,
        )
    return targets


def ensure_allowed_path(candidate: Path, allowed_roots: list[Path]) -> Path:
    """解析并验证写入路径位于至少一个允许目录内。"""

    resolved = candidate.resolve()
    roots = [root.resolve() for root in allowed_roots]
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise ValueError(f"路径不在允许写入范围：{resolved}")
    return resolved

