import asyncio
import json
from pathlib import Path

import pytest

from scripts.repair_evaluation_gaps import build_audit_manifest, staged_result_path
from src.evaluation.repair.models import Gap
from src.evaluation.repair.runner import RepairRunner
from src.evaluation.repair.validation import apply_staged, validate_staged


def _gap(index: int, round_number: int = 1) -> Gap:
    return Gap(
        target_key="three-journals-six",
        paper_id=index,
        dimension="problem_originality",
        round_number=round_number,
        model="glm-5.1",
        reason="missing_score",
    )


@pytest.mark.asyncio
async def test_runner_limits_peak_api_concurrency(tmp_path: Path) -> None:
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def call(gap: Gap) -> dict:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.01)
        async with lock:
            active -= 1
        return {"score": 70 + gap.paper_id % 10}

    runner = RepairRunner(
        checkpoint_path=tmp_path / "checkpoint.json",
        api_concurrency=3,
        max_attempts=1,
    )
    result = await runner.run([_gap(index) for index in range(12)], call)

    assert peak == 3
    assert result.succeeded == 12
    assert result.failed == 0


@pytest.mark.asyncio
async def test_runner_finishes_r1_before_scheduling_r2(tmp_path: Path) -> None:
    events: list[str] = []
    r1_finished: set[int] = set()

    async def call(gap: Gap) -> dict:
        if gap.round_number == 2:
            assert gap.paper_id in r1_finished
            events.append(f"r2-start-{gap.paper_id}")
            return {"revised_score": 72}
        await asyncio.sleep(0.01)
        r1_finished.add(gap.paper_id)
        events.append(f"r1-end-{gap.paper_id}")
        return {"score": 70}

    gaps = [_gap(1, 2), _gap(2, 1), _gap(1, 1)]
    runner = RepairRunner(
        checkpoint_path=tmp_path / "checkpoint.json",
        api_concurrency=2,
        max_attempts=1,
    )
    await runner.run(gaps, call)

    assert events.index("r1-end-1") < events.index("r2-start-1")


@pytest.mark.asyncio
async def test_runner_resumes_successful_checkpoint_without_recalling(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    gap = _gap(3)
    checkpoint.write_text(
        json.dumps(
            {
                "version": 1,
                "slots": {
                    gap.slot_key: {
                        "status": "success",
                        "response": {"score": 81},
                        "attempts": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    async def call(_: Gap) -> dict:
        nonlocal calls
        calls += 1
        return {"score": 99}

    runner = RepairRunner(
        checkpoint_path=checkpoint,
        api_concurrency=1,
        max_attempts=1,
    )
    result = await runner.run([gap], call)

    assert calls == 0
    assert result.responses[gap.slot_key] == {"score": 81}


@pytest.mark.asyncio
async def test_runner_retries_then_records_failure(tmp_path: Path) -> None:
    calls = 0

    async def call(_: Gap) -> dict:
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary")

    runner = RepairRunner(
        checkpoint_path=tmp_path / "checkpoint.json",
        api_concurrency=1,
        max_attempts=2,
        retry_delay_seconds=0,
    )
    result = await runner.run([_gap(4)], call)

    assert calls == 2
    assert result.failed == 1
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["slots"][_gap(4).slot_key]["status"] == "failed"
    assert saved["slots"][_gap(4).slot_key]["attempts"] == 2


def test_audit_manifest_scans_partial_file_instead_of_skipping_it(
    tmp_path: Path,
) -> None:
    per_paper = (
        tmp_path
        / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper"
    )
    per_paper.mkdir(parents=True)
    payload = {
        "paper": "raw/paper.pdf",
        "dimensions": {
            "problem_originality": {
                "round1_scores": {
                    "deepseek-v4-pro": 70,
                    "glm-5.1": 75,
                    "kimi-k2.6": 72,
                },
                "round2_scores": {
                    "deepseek-v4-pro": 71,
                    "glm-5.1": 74,
                },
            }
        },
    }
    (per_paper / "paper-344.json").write_text(json.dumps(payload), encoding="utf-8")

    manifest = build_audit_manifest(
        tmp_path,
        target_keys=["three-journals-six"],
    )

    assert manifest["summary"]["gap_count"] == 3
    assert {gap["round_number"] for gap in manifest["gaps"]} == {1, 2}
    assert manifest["sources"]["three-journals-six:344"]["sha256"]


def test_audit_manifest_reports_expected_paper_file_that_is_entirely_missing(
    tmp_path: Path,
) -> None:
    target_dir = (
        tmp_path
        / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper"
    )
    target_dir.mkdir(parents=True)
    summary = target_dir.parent / "summary.csv"
    summary.write_text("paper_id,ccb_score\n1,80\n2,81\n", encoding="utf-8")
    (target_dir / "paper-1.json").write_text(
        json.dumps({"dimensions": {}}, ensure_ascii=False), encoding="utf-8"
    )

    manifest = build_audit_manifest(
        tmp_path,
        target_keys=["three-journals-six"],
    )

    assert manifest["summary"]["missing_file_count"] == 1
    assert manifest["structure_errors"] == [
        {
            "target_key": "three-journals-six",
            "paper_id": 2,
            "reason": "missing_result_file",
        }
    ]


def test_staged_result_path_is_namespaced_by_target(tmp_path: Path) -> None:
    path = staged_result_path(tmp_path, "e2-r2", 205)

    assert path == tmp_path / "staged/e2-r2/paper-205.json"


def _prepare_validation_fixture(tmp_path: Path) -> tuple[Path, Path, dict]:
    per_paper = (
        tmp_path
        / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper"
    )
    per_paper.mkdir(parents=True)
    source = per_paper / "paper-344.json"
    original = {
        "paper": "raw/paper.pdf",
        "dimensions": {
            "problem_originality": {
                "round1_scores": {
                    "deepseek-v4-pro": 70,
                    "glm-5.1": 75,
                    "kimi-k2.6": 72,
                },
                "round2_scores": {
                    "deepseek-v4-pro": 71,
                    "glm-5.1": 74,
                },
            }
        },
        "overall": {},
    }
    source.write_text(json.dumps(original), encoding="utf-8")
    output = tmp_path / "results/runs/repair"
    output.mkdir(parents=True)
    manifest = build_audit_manifest(
        tmp_path,
        target_keys=["three-journals-six"],
    )
    (output / "repair-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    staged = staged_result_path(output, "three-journals-six", 344)
    staged.parent.mkdir(parents=True)
    repaired = json.loads(json.dumps(original))
    dimension = repaired["dimensions"]["problem_originality"]
    dimension["round1_scores"]["qwen3.6-plus"] = 77
    dimension["round2_scores"].update(
        {"kimi-k2.6": 73, "qwen3.6-plus": 76}
    )
    staged.write_text(json.dumps(repaired), encoding="utf-8")
    (output / "run-report.json").write_text(
        json.dumps(
            {
                "staged_files": [
                    {
                        "target_key": "three-journals-six",
                        "paper_id": 344,
                        "staged_path": str(staged),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return output, source, original


def test_validation_accepts_only_missing_slot_additions(tmp_path: Path) -> None:
    output, _, _ = _prepare_validation_fixture(tmp_path)

    report = validate_staged(tmp_path, output)

    assert report["valid"] is True
    assert report["unresolved_gap_count"] == 0


def test_validation_rejects_change_to_existing_valid_score(tmp_path: Path) -> None:
    output, _, _ = _prepare_validation_fixture(tmp_path)
    staged = staged_result_path(output, "three-journals-six", 344)
    payload = json.loads(staged.read_text(encoding="utf-8"))
    payload["dimensions"]["problem_originality"]["round1_scores"][
        "deepseek-v4-pro"
    ] = 99
    staged.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_staged(tmp_path, output)

    assert report["valid"] is False
    assert any("已有有效评分被修改" in error for error in report["errors"])


def test_validation_rejects_staged_path_outside_output_namespace(
    tmp_path: Path,
) -> None:
    output, _, _ = _prepare_validation_fixture(tmp_path)
    report_path = output / "run-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["staged_files"][0]["staged_path"] = str(tmp_path / "elsewhere.json")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    validation = validate_staged(tmp_path, output)

    assert validation["valid"] is False
    assert any("不在允许写入范围" in error for error in validation["errors"])


def test_apply_creates_backup_and_replaces_source_after_validation(
    tmp_path: Path,
) -> None:
    output, source, original = _prepare_validation_fixture(tmp_path)
    validate_staged(tmp_path, output)

    report = apply_staged(tmp_path, output)

    applied = json.loads(source.read_text(encoding="utf-8"))
    backup = output / "backups/three-journals-six/paper-344.json"
    assert report["applied_count"] == 1
    assert applied["dimensions"]["problem_originality"]["round2_scores"][
        "qwen3.6-plus"
    ] == 76
    assert json.loads(backup.read_text(encoding="utf-8")) == original
