"""暂存结果验证、备份与原子应用。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.evaluation.repair.five_axis import (
    is_valid_position_output,
    scan_five_axis_gaps,
)
from src.evaluation.repair.registry import ensure_allowed_path, target_registry
from src.evaluation.repair.runner import atomic_write_json
from src.evaluation.repair.six_dimension import (
    is_valid_score,
    scan_six_dimension_gaps,
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 顶层不是 object：{path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _six_score_maps(result: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    dimensions = result.get("dimensions", {})
    if not isinstance(dimensions, Mapping):
        return
    for dimension_key, dimension in dimensions.items():
        if not isinstance(dimension, Mapping):
            continue
        r1_field = (
            "model_scores"
            if "model_scores" in dimension and "round1_scores" not in dimension
            else "round1_scores"
        )
        for round_number, field in ((1, r1_field), (2, "round2_scores")):
            scores = dimension.get(field, {})
            if isinstance(scores, Mapping):
                yield f"{dimension_key}:r{round_number}", scores


def _preserved_six_scores(
    original: Mapping[str, Any], staged: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    staged_maps = dict(_six_score_maps(staged))
    for location, scores in _six_score_maps(original):
        new_scores = staged_maps.get(location, {})
        for model, value in scores.items():
            if is_valid_score(value) and new_scores.get(model) != value:
                errors.append(
                    f"已有有效评分被修改：{location}:{model} {value!r}→{new_scores.get(model)!r}"
                )
    return errors


def _preserved_five_outputs(
    original: Mapping[str, Any], staged: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    for round_key in ("round1", "round2"):
        old_round = original.get(round_key)
        new_round = staged.get(round_key)
        old_models = old_round.get("models", {}) if isinstance(old_round, Mapping) else {}
        new_models = new_round.get("models", {}) if isinstance(new_round, Mapping) else {}
        for model, output in old_models.items():
            if is_valid_position_output(output) and new_models.get(model) != output:
                errors.append(f"已有有效五轴输出被修改：{round_key}:{model}")
    return errors


def validate_staged(project_root: Path, output_dir: Path) -> dict[str, Any]:
    """验证暂存结果只补缺口、源文件未漂移且目标文件不再缺槽位。"""

    root = project_root.resolve()
    out = output_dir.resolve()
    manifest = _load_json(out / "repair-manifest.json")
    run_report = _load_json(out / "run-report.json")
    registry = target_registry(root)
    errors: list[str] = []
    unresolved: list[str] = []
    checked: list[dict[str, Any]] = []
    sources = manifest.get("sources", {})
    staged_index: dict[tuple[str, int], Path] = {}
    for entry in run_report.get("staged_files", []):
        key = (entry["target_key"], int(entry["paper_id"]))
        try:
            staged_index[key] = ensure_allowed_path(
                Path(entry["staged_path"]), [out / "staged"]
            )
        except ValueError as exc:
            errors.append(str(exc))

    expected_files = {
        (gap["target_key"], int(gap["paper_id"])) for gap in manifest.get("gaps", [])
    }
    for key in sorted(expected_files):
        if key not in staged_index:
            errors.append(f"缺少暂存文件：{key[0]}:paper-{key[1]}")

    for (target_key, paper_id), staged_path in sorted(staged_index.items()):
        target = registry.get(target_key)
        if target is None:
            errors.append(f"未知暂存目标：{target_key}")
            continue
        source = target.per_paper_dir / f"paper-{paper_id}.json"
        source_info = sources.get(f"{target_key}:{paper_id}", {})
        if not source.exists() or not staged_path.exists():
            errors.append(f"源文件或暂存文件不存在：{target_key}:paper-{paper_id}")
            continue
        current_sha = _sha256(source)
        if current_sha != source_info.get("sha256"):
            errors.append(f"源文件在审计后发生变化：{source}")
            continue
        original = _load_json(source)
        staged = _load_json(staged_path)
        if target.family == "five_axis":
            errors.extend(
                f"{target_key}:paper-{paper_id}: {error}"
                for error in _preserved_five_outputs(original, staged)
            )
            remaining = scan_five_axis_gaps(target, paper_id, staged)
        else:
            errors.extend(
                f"{target_key}:paper-{paper_id}: {error}"
                for error in _preserved_six_scores(original, staged)
            )
            remaining = scan_six_dimension_gaps(target, paper_id, staged)
        unresolved.extend(gap.slot_key for gap in remaining)
        checked.append(
            {
                "target_key": target_key,
                "paper_id": paper_id,
                "source_path": str(source),
                "source_sha256": current_sha,
                "staged_path": str(staged_path),
                "staged_sha256": _sha256(staged_path),
                "remaining_gaps": len(remaining),
            }
        )

    if unresolved:
        errors.append(f"仍有 {len(unresolved)} 个未解决槽位")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "valid": not errors,
        "checked_file_count": len(checked),
        "unresolved_gap_count": len(unresolved),
        "unresolved_gaps": unresolved,
        "errors": errors,
        "files": checked,
    }
    atomic_write_json(out / "validation-report.json", report)
    return report


def apply_staged(project_root: Path, output_dir: Path) -> dict[str, Any]:
    """验证通过后备份并原子替换权威逐篇文件。"""

    root = project_root.resolve()
    out = output_dir.resolve()
    validation = _load_json(out / "validation-report.json")
    if not validation.get("valid"):
        raise ValueError("validation-report 未通过，拒绝 apply")
    registry = target_registry(root)
    allowed_roots = [target.per_paper_dir for target in registry.values()]
    applied: list[dict[str, Any]] = []
    for entry in validation.get("files", []):
        target_key = entry["target_key"]
        paper_id = int(entry["paper_id"])
        source = ensure_allowed_path(Path(entry["source_path"]), allowed_roots)
        staged = ensure_allowed_path(Path(entry["staged_path"]), [out / "staged"])
        if _sha256(source) != entry["source_sha256"]:
            raise ValueError(f"apply 前源文件发生变化：{source}")
        if _sha256(staged) != entry["staged_sha256"]:
            raise ValueError(f"apply 前暂存文件发生变化：{staged}")
        backup = out / "backups" / target_key / f"paper-{paper_id}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        temporary = source.with_name(f".{source.name}.repair.tmp")
        shutil.copy2(staged, temporary)
        os.replace(temporary, source)
        applied.append(
            {
                "target_key": target_key,
                "paper_id": paper_id,
                "source_path": str(source),
                "backup_path": str(backup),
                "before_sha256": entry["source_sha256"],
                "after_sha256": _sha256(source),
            }
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied_count": len(applied),
        "files": applied,
    }
    atomic_write_json(out / "apply-report.json", report)
    return report
