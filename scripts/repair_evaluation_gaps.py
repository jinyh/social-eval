#!/usr/bin/env python3
"""审计并槽位级修复六维、五轴与 E2 评价结果。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.repair.five_axis import scan_five_axis_gaps  # noqa: E402
from src.evaluation.repair.models import Gap  # noqa: E402
from src.evaluation.repair.registry import target_registry  # noqa: E402
from src.evaluation.repair.runner import RepairRunner, atomic_write_json  # noqa: E402
from src.evaluation.repair.runtime import RepairRuntime  # noqa: E402
from src.evaluation.repair.six_dimension import scan_six_dimension_gaps  # noqa: E402
from src.evaluation.repair.validation import apply_staged, validate_staged  # noqa: E402

DEFAULT_TARGET_KEYS = (
    "three-journals-six",
    "jiaodafaxue-six",
    "xueshuyuekan-six",
    "three-journals-five",
    "jiaodafaxue-five",
    "xueshuyuekan-five",
    "e2-r1",
    "e2-r2",
)
DEFAULT_OUTPUT_DIR = Path("results/runs/completeness-repair-20260716")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paper_id(path: Path) -> int:
    try:
        return int(path.stem.removeprefix("paper-"))
    except ValueError as exc:
        raise ValueError(f"无法从文件名解析 paper id：{path.name}") from exc


def _relative_or_absolute(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def build_audit_manifest(
    project_root: Path,
    *,
    target_keys: list[str] | tuple[str, ...] = DEFAULT_TARGET_KEYS,
    paper_ids: set[int] | None = None,
) -> dict[str, Any]:
    """只读扫描权威逐篇文件并返回稳定缺口清单。"""

    root = project_root.resolve()
    registry = target_registry(root)
    unknown = sorted(set(target_keys) - set(registry))
    if unknown:
        raise KeyError(f"未知修复目标：{', '.join(unknown)}")

    gaps = []
    sources: dict[str, dict[str, Any]] = {}
    target_file_counts: Counter[str] = Counter()
    target_gap_counts: Counter[str] = Counter()
    structure_errors: list[dict[str, Any]] = []
    for target_key in target_keys:
        target = registry[target_key]
        expected_ids = set(target.expected_paper_ids)
        if paper_ids is not None:
            expected_ids &= paper_ids
        existing_ids = {
            _paper_id(path) for path in target.per_paper_dir.glob("paper-*.json")
        }
        for missing_id in sorted(expected_ids - existing_ids):
            structure_errors.append(
                {
                    "target_key": target_key,
                    "paper_id": missing_id,
                    "reason": "missing_result_file",
                }
            )
        for path in sorted(target.per_paper_dir.glob("paper-*.json")):
            pid = _paper_id(path)
            if paper_ids is not None and pid not in paper_ids:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if target.family == "five_axis":
                file_gaps = scan_five_axis_gaps(target, pid, payload)
            else:
                file_gaps = scan_six_dimension_gaps(target, pid, payload)
            target_file_counts[target_key] += 1
            target_gap_counts[target_key] += len(file_gaps)
            source_key = f"{target_key}:{pid}"
            sources[source_key] = {
                "target_key": target_key,
                "paper_id": pid,
                "path": _relative_or_absolute(path, root),
                "sha256": _sha256(path),
                "gap_count": len(file_gaps),
            }
            gaps.extend(asdict(gap) for gap in file_gaps)

    gaps.sort(
        key=lambda gap: (
            gap["round_number"],
            gap["target_key"],
            gap["paper_id"],
            gap["dimension"],
            gap["model"],
        )
    )
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "target_keys": list(target_keys),
        "summary": {
            "source_file_count": len(sources),
            "gap_count": len(gaps),
            "missing_file_count": len(structure_errors),
            "files_by_target": dict(target_file_counts),
            "gaps_by_target": dict(target_gap_counts),
        },
        "sources": sources,
        "gaps": gaps,
        "structure_errors": structure_errors,
    }


def staged_result_path(output_dir: Path, target_key: str, paper_id: int) -> Path:
    """返回按目标隔离的暂存结果路径。"""

    return output_dir / "staged" / target_key / f"paper-{paper_id}.json"


def _resolve_output_dir(project_root: Path, output_dir: Path) -> Path:
    return output_dir if output_dir.is_absolute() else project_root / output_dir


def command_audit(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    output_dir = _resolve_output_dir(root, args.output_dir)
    paper_ids = set(args.pids) if args.pids else None
    manifest = build_audit_manifest(
        root,
        target_keys=args.targets,
        paper_ids=paper_ids,
    )
    manifest_path = output_dir / "repair-manifest.json"
    atomic_write_json(manifest_path, manifest)
    print(f"审计文件：{manifest_path}")
    print(f"源文件：{manifest['summary']['source_file_count']}")
    print(f"缺失槽位：{manifest['summary']['gap_count']}")
    print(f"结构错误：{manifest['summary']['missing_file_count']}")
    for key, count in manifest["summary"]["gaps_by_target"].items():
        print(f"  {key}: {count}")
    return 1 if manifest["structure_errors"] else 0


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取修复清单：{path}") from exc
    if manifest.get("version") != 1 or not isinstance(manifest.get("gaps"), list):
        raise ValueError(f"修复清单格式不支持：{path}")
    return manifest


def _manifest_gaps(manifest: dict[str, Any]) -> list[Gap]:
    return [Gap(**payload) for payload in manifest["gaps"]]


async def _run_repair(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    output_dir = _resolve_output_dir(root, args.output_dir)
    manifest_path = args.manifest or output_dir / "repair-manifest.json"
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest = _load_manifest(manifest_path)
    if Path(manifest["project_root"]).resolve() != root:
        raise ValueError("repair manifest 的 project_root 与本次运行不一致")
    gaps = _manifest_gaps(manifest)
    checkpoint_path = output_dir / "checkpoint.json"
    runtime = RepairRuntime(root, gaps)
    runner = RepairRunner(
        checkpoint_path=checkpoint_path,
        api_concurrency=args.api_concurrency,
        max_attempts=args.max_attempts,
        retry_delay_seconds=args.retry_delay,
    )

    round1 = [gap for gap in gaps if gap.round_number == 1]
    original_round2 = [gap for gap in gaps if gap.round_number == 2]
    runtime.apply_checkpoint(round1, checkpoint_path)
    r1_result = await runner.run(round1, runtime.call_gap)

    dynamic_round2 = runtime.prepare_five_axis_round2()
    round2_by_slot = {
        gap.slot_key: gap for gap in [*original_round2, *dynamic_round2]
    }
    round2 = list(round2_by_slot.values())
    runtime.apply_checkpoint(round2, checkpoint_path)
    r2_result = await runner.run(round2, runtime.call_gap)

    runtime.finalize()
    staged = runtime.write_staged(output_dir)
    errors = {**r1_result.errors, **r2_result.errors}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "api_concurrency": args.api_concurrency,
        "initial_gap_count": len(gaps),
        "dynamic_round2_gap_count": len(dynamic_round2),
        "succeeded": r1_result.succeeded + r2_result.succeeded,
        "failed": len(errors),
        "errors": errors,
        "staged_files": staged,
    }
    atomic_write_json(output_dir / "run-report.json", report)
    print(f"R1 成功/失败：{r1_result.succeeded}/{r1_result.failed}")
    print(f"R2 成功/失败：{r2_result.succeeded}/{r2_result.failed}")
    print(f"动态五轴 R2 槽位：{len(dynamic_round2)}")
    print(f"暂存文件：{len(staged)}")
    print(f"运行报告：{output_dir / 'run-report.json'}")
    return 1 if errors else 0


def command_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run_repair(args))


def command_validate(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    output_dir = _resolve_output_dir(root, args.output_dir)
    report = validate_staged(root, output_dir)
    print(f"校验文件：{output_dir / 'validation-report.json'}")
    print(f"校验结果：{'通过' if report['valid'] else '失败'}")
    print(f"检查文件：{report['checked_file_count']}")
    print(f"残余槽位：{report['unresolved_gap_count']}")
    for error in report["errors"][:20]:
        print(f"  - {error}")
    return 0 if report["valid"] else 1


def command_apply(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    output_dir = _resolve_output_dir(root, args.output_dir)
    report = apply_staged(root, output_dir)
    print(f"已应用文件：{report['applied_count']}")
    print(f"应用报告：{output_dir / 'apply-report.json'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="只读扫描缺失槽位")
    audit.add_argument(
        "--targets",
        nargs="+",
        choices=DEFAULT_TARGET_KEYS,
        default=list(DEFAULT_TARGET_KEYS),
    )
    audit.add_argument("--pids", nargs="+", type=int)
    audit.set_defaults(handler=command_audit)

    run = subparsers.add_parser("run", help="按清单调用模型并写入暂存副本")
    run.add_argument("--manifest", type=Path)
    run.add_argument("--api-concurrency", type=int, default=12)
    run.add_argument("--max-attempts", type=int, default=2)
    run.add_argument("--retry-delay", type=float, default=1.0)
    run.set_defaults(handler=command_run)

    validate = subparsers.add_parser("validate", help="验证暂存副本")
    validate.set_defaults(handler=command_validate)

    apply_parser = subparsers.add_parser("apply", help="备份并应用已验证副本")
    apply_parser.set_defaults(handler=command_apply)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
