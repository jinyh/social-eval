"""框架、代码入口与活动结果的一一对应审计。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from src.evaluation.repair.five_axis import scan_five_axis_gaps
from src.evaluation.repair.registry import target_registry
from src.evaluation.repair.six_dimension import scan_six_dimension_gaps
from src.knowledge.loader import load_framework
from src.knowledge.registry import (
    assert_embedded_scoring_protocols_match,
    load_position_framework,
    load_registry,
    load_review_protocol,
    load_scoring_protocol,
)

SIX_DIMENSION_MODELS = {
    "deepseek-v4-pro",
    "glm-5.1",
    "kimi-k2.6",
    "qwen3.6-plus",
}


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


def raw_payload_coverage(
    payloads: list[dict[str, Any]],
    dimension_keys: tuple[str, ...],
    *,
    mode: str,
    expected_payload_count: int | None = None,
) -> dict[str, int]:
    """统计历史逐模型原始响应；与评分槽位完整性分开报告。"""

    paper_count = len(payloads) if expected_payload_count is None else expected_payload_count
    expected = paper_count * len(dimension_keys) * len(SIX_DIMENSION_MODELS)
    present = 0
    for payload in payloads:
        dimensions = payload.get("dimensions", {})
        if not isinstance(dimensions, dict):
            dimensions = {}
        for key in dimension_keys:
            dimension = dimensions.get(key, {})
            if not isinstance(dimension, dict):
                continue
            shared = dimension.get("raw_outputs", {})
            shared = shared if isinstance(shared, dict) else {}
            explicit_r2 = dimension.get("round2_raw_outputs", {})
            explicit_r2 = explicit_r2 if isinstance(explicit_r2, dict) else {}
            if mode == "shared":
                raw = shared
            elif mode == "explicit_r2":
                raw = explicit_r2
            elif mode == "e2_r2":
                # 新格式完整保存 round2_raw_outputs；旧格式把 R2 放在
                # raw_outputs，补测槽位另写 round2_raw_outputs。
                raw = (
                    explicit_r2
                    if SIX_DIMENSION_MODELS.issubset(explicit_r2)
                    else shared | explicit_r2
                )
            else:
                raise ValueError(f"未知原始响应统计模式: {mode}")
            present += sum(
                isinstance(raw.get(model), dict) for model in SIX_DIMENSION_MODELS
            )
    return {"expected": expected, "present": present, "missing": expected - present}


def _load_json_paths(paths: list[Path]) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in paths if path.exists()
    ]


def audit_active_results(project_root: Path) -> dict[str, Any]:
    """只读审计注册框架、数据集摘要、排名和可用逐篇结果。"""

    root = project_root.resolve()
    six_dimension_keys = tuple(
        dimension.key
        for dimension in load_framework(
            root / "configs/frameworks/law-v2.55-cross-review.yaml"
        ).dimensions
    )
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

    score_slots: dict[str, dict[str, int]] = {}
    for target_key, target in target_registry(root).items():
        if not target.per_paper_dir.exists():
            score_slots[target_key] = {"files": 0, "gaps": 0, "missing_files": 0}
            continue
        paths = {
            int(path.stem.removeprefix("paper-")): path
            for path in target.per_paper_dir.glob("paper-*.json")
        }
        expected_ids = set(target.expected_paper_ids)
        missing_files = len(expected_ids - set(paths))
        gaps = 0
        for pid, path in paths.items():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if target.family == "five_axis":
                gaps += len(scan_five_axis_gaps(target, pid, payload))
            else:
                gaps += len(scan_six_dimension_gaps(target, pid, payload))
        score_slots[target_key] = {
            "files": len(paths),
            "gaps": gaps,
            "missing_files": missing_files,
        }
        if gaps:
            errors.append(f"{target_key}: {gaps} 个评分槽位缺失")
        if missing_files:
            errors.append(f"{target_key}: {missing_files} 个逐篇文件缺失")

    raw_payload_slots: dict[str, dict[str, dict[str, int]]] = {}
    for dataset in ("three-journals", "jiaodafaxue", "xueshuyuekan"):
        base = (
            root
            / "results/datasets"
            / dataset
            / "six-dimension/phase2-r2-v2.55"
        )
        per_paper_paths = sorted((base / "per-paper").glob("paper-*.json"))
        if dataset == "xueshuyuekan":
            r1_payloads = _load_json_paths(per_paper_paths)
            r1_mode = "shared"
            r2_payloads = r1_payloads
            r2_mode = "explicit_r2"
        else:
            r1_paths = sorted((base / "audit/round1-standalone").glob("paper-*.json"))
            r1_paths.extend(sorted((base / "audit/round1-errors").glob("*/paper-*.json")))
            r1_payloads = _load_json_paths(r1_paths)
            r1_mode = "shared"
            r2_payloads = _load_json_paths(per_paper_paths)
            r2_mode = "shared"
        raw_payload_slots[dataset] = {
            "round1": raw_payload_coverage(
                r1_payloads,
                six_dimension_keys,
                mode=r1_mode,
                expected_payload_count=datasets[dataset]["six_dimension"],
            ),
            "round2": raw_payload_coverage(
                r2_payloads,
                six_dimension_keys,
                mode=r2_mode,
                expected_payload_count=datasets[dataset]["six_dimension"],
            ),
        }

    e2_ids = sorted(pool_ids)
    e2_base = root / "results/rankings/e2-ccb-v5/per-paper"
    e2_r1 = _load_json_paths(
        [e2_base / "round1" / f"paper-{pid}.json" for pid in e2_ids]
    )
    e2_r2 = _load_json_paths(
        [e2_base / "round2" / f"paper-{pid}.json" for pid in e2_ids]
    )
    raw_payload_slots["e2"] = {
        "round1": raw_payload_coverage(
            e2_r1,
            six_dimension_keys,
            mode="shared",
            expected_payload_count=len(e2_ids),
        ),
        "round2": raw_payload_coverage(
            e2_r2,
            six_dimension_keys,
            mode="e2_r2",
            expected_payload_count=len(e2_ids),
        ),
    }
    for dataset, rounds in raw_payload_slots.items():
        for round_name, coverage in rounds.items():
            if coverage["missing"]:
                warnings.append(
                    f"{dataset}.{round_name}: {coverage['missing']} 个历史原始响应缺失；"
                    "评分槽位完整性不受影响"
                )

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
        "score_slots": score_slots,
        "raw_payload_slots": raw_payload_slots,
        "e2": {
            "pool_count": len(pool),
            "ranking_count": len(ranking["papers"]),
        },
    }
