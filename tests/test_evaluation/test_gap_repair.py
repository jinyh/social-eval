from pathlib import Path

import pytest

from src.evaluation.repair.models import Gap, RepairTarget
from src.evaluation.repair.five_axis import (
    build_skip_round2,
    merge_five_axis_response,
    rebuild_five_axis_record,
    scan_five_axis_gaps,
)
from src.evaluation.repair.registry import ensure_allowed_path, target_registry
from src.evaluation.repair.runtime import compact_paper_for_content_inspection
from src.evaluation.repair.six_dimension import (
    merge_model_response,
    recompute_result_statistics,
    scan_six_dimension_gaps,
)
from src.ingestion.schemas import ProcessedPaper


MODELS = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]


def _standard_result() -> dict:
    return {
        "paper": "raw/paper.pdf",
        "dimensions": {
            "problem_originality": {
                "round1_scores": {
                    "deepseek-v4-pro": 70,
                    "glm-5.1": 80,
                    "kimi-k2.6": 75,
                },
                "round2_scores": {
                    "deepseek-v4-pro": 72,
                    "glm-5.1": 78,
                },
                "raw_outputs": {
                    "deepseek-v4-pro": {"score": 70},
                    "glm-5.1": {"score": 80},
                    "kimi-k2.6": {"score": 75},
                },
                "errors": {"qwen3.6-plus": "timeout"},
                "changes": {},
            }
        },
        "overall": {},
    }


def _legacy_r1_result() -> dict:
    return {
        "paper": "raw/paper.pdf",
        "dimensions": {
            "problem_originality": {
                "model_scores": {
                    "deepseek-v4-pro": 70,
                    "glm-5.1": 80,
                    "kimi-k2.6": 75,
                },
                "raw_outputs": {
                    "deepseek-v4-pro": {"score": 70},
                    "glm-5.1": {"score": 80},
                    "kimi-k2.6": {"score": 75},
                },
                "errors": {},
            }
        },
        "overall": {},
    }


def _five_axis_result_with_error() -> dict:
    axes = {
        key: {"score": 2, "evidence_quotes": ["证据"], "rationale": "理由"}
        for key in (
            "object_belonging",
            "material_belonging",
            "category_autonomy",
            "explanatory_orientation",
            "system_mappability",
        )
    }
    valid = {
        "research_route": {"primary": "chinese_doctrinal"},
        "axis_scores": axes,
        "total_score": 10,
        "confidence": "high",
        "review_required": False,
    }
    return {
        "paper_id": 99,
        "paper": "paper.md",
        "round2_mode": "not_run",
        "round1": {
            "paper_id": 99,
            "paper": "paper.md",
            "models": {
                "deepseek-v4-pro": valid,
                "qwen3.6-plus": {"error": "JSON parse failed"},
            },
        },
        "round2": None,
        "final": {"per_model_total_scores": {"deepseek-v4-pro": 10}},
    }


def test_registry_resolves_all_targets_from_project_root(tmp_path: Path) -> None:
    registry = target_registry(tmp_path)

    assert registry["three-journals-six"].per_paper_dir == (
        tmp_path
        / "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper"
    )
    assert registry["jiaodafaxue-five"].per_paper_dir == (
        tmp_path
        / "results/datasets/jiaodafaxue/five-axis/position-v0.2/per-paper"
    )
    assert registry["xueshuyuekan-six"].dataset == "xueshuyuekan"
    assert registry["e2-r1"].round_number == 1
    assert registry["e2-r2"].round_number == 2


def test_registry_models_are_immutable_value_objects(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["three-journals-six"]
    gap = Gap(
        target_key=target.key,
        paper_id=344,
        dimension="problem_originality",
        round_number=2,
        model="glm-5.1",
        reason="missing_score",
    )

    assert isinstance(target, RepairTarget)
    assert gap.slot_key == "three-journals-six:344:problem_originality:r2:glm-5.1"
    with pytest.raises(AttributeError):
        target.dataset = "changed"  # type: ignore[misc]


def test_unknown_registry_key_is_not_silently_created(tmp_path: Path) -> None:
    registry = target_registry(tmp_path)

    with pytest.raises(KeyError):
        _ = registry["unknown"]


def test_path_guard_accepts_registered_descendant(tmp_path: Path) -> None:
    allowed = tmp_path / "results/datasets/three-journals"
    candidate = allowed / "six-dimension/run/per-paper/paper-1.json"

    assert ensure_allowed_path(candidate, [allowed]) == candidate.resolve()


def test_path_guard_rejects_prefix_collision_and_parent_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "results/datasets/three-journals"

    with pytest.raises(ValueError, match="不在允许写入范围"):
        ensure_allowed_path(
            tmp_path / "results/datasets/three-journals-evil/paper-1.json",
            [allowed],
        )
    with pytest.raises(ValueError, match="不在允许写入范围"):
        ensure_allowed_path(allowed / "../secret.json", [allowed])


def test_scan_standard_result_reports_only_missing_score_slots(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["three-journals-six"]

    gaps = scan_six_dimension_gaps(target, 344, _standard_result())

    assert {(gap.round_number, gap.model) for gap in gaps} == {
        (1, "qwen3.6-plus"),
        (2, "kimi-k2.6"),
        (2, "qwen3.6-plus"),
    }


def test_scan_legacy_e2_r1_uses_model_scores(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["e2-r1"]

    gaps = scan_six_dimension_gaps(target, 205, _legacy_r1_result())

    assert len(gaps) == 1
    assert gaps[0].round_number == 1
    assert gaps[0].model == "qwen3.6-plus"


def test_scan_e2_r2_only_checks_requested_round(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["e2-r2"]

    gaps = scan_six_dimension_gaps(target, 205, _standard_result())

    assert {(gap.round_number, gap.model) for gap in gaps} == {
        (2, "kimi-k2.6"),
        (2, "qwen3.6-plus"),
    }


def test_invalid_score_is_a_gap_even_when_model_key_exists(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["three-journals-six"]
    result = _standard_result()
    result["dimensions"]["problem_originality"]["round1_scores"][
        "qwen3.6-plus"
    ] = None

    gaps = scan_six_dimension_gaps(target, 344, result)

    qwen_r1 = [g for g in gaps if g.round_number == 1 and g.model == "qwen3.6-plus"]
    assert qwen_r1[0].reason == "invalid_score"


def test_merge_r1_response_preserves_existing_values_and_raw_output(
    tmp_path: Path,
) -> None:
    target = target_registry(tmp_path)["three-journals-six"]
    original = _standard_result()
    gap = next(
        gap
        for gap in scan_six_dimension_gaps(target, 344, original)
        if gap.round_number == 1
    )

    merged = merge_model_response(
        original,
        gap,
        {"score": 77, "rationale": "补测理由"},
        elapsed_seconds=1.5,
    )

    dimension = merged["dimensions"]["problem_originality"]
    assert original["dimensions"]["problem_originality"]["round1_scores"] == {
        "deepseek-v4-pro": 70,
        "glm-5.1": 80,
        "kimi-k2.6": 75,
    }
    assert dimension["round1_scores"]["deepseek-v4-pro"] == 70
    assert dimension["round1_scores"]["qwen3.6-plus"] == 77
    assert dimension["raw_outputs"]["qwen3.6-plus"]["rationale"] == "补测理由"
    assert "qwen3.6-plus" not in dimension["errors"]


def test_merge_r2_response_persists_raw_response_and_recomputes_statistics(
    tmp_path: Path,
) -> None:
    target = target_registry(tmp_path)["three-journals-six"]
    original = _standard_result()
    gap = next(
        gap
        for gap in scan_six_dimension_gaps(target, 344, original)
        if gap.round_number == 2 and gap.model == "kimi-k2.6"
    )

    merged = merge_model_response(
        original,
        gap,
        {
            "revised_score": 74,
            "score_changed": True,
            "change_direction": "down",
            "change_magnitude": 1,
        },
        elapsed_seconds=2.0,
    )
    recomputed = recompute_result_statistics(merged)
    dimension = recomputed["dimensions"]["problem_originality"]

    assert dimension["round2_scores"]["kimi-k2.6"] == 74
    assert dimension["round2_raw_outputs"]["kimi-k2.6"]["revised_score"] == 74
    assert dimension["changes"]["kimi-k2.6"]["original"] == 75
    assert dimension["round1_mean"] == 75
    assert dimension["round2_mean"] == pytest.approx(74.7, abs=0.01)
    assert recomputed["overall"]["dimensions_converged"] == 1


def test_merge_refuses_to_overwrite_an_existing_valid_score(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["three-journals-six"]
    result = _standard_result()
    gap = Gap(
        target_key=target.key,
        paper_id=344,
        dimension="problem_originality",
        round_number=1,
        model="deepseek-v4-pro",
        reason="forced",
    )

    with pytest.raises(ValueError, match="拒绝覆盖已有有效评分"):
        merge_model_response(result, gap, {"score": 99}, elapsed_seconds=1.0)


def test_five_axis_error_output_is_reported_as_r1_gap(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["jiaodafaxue-five"]

    gaps = scan_five_axis_gaps(target, 99, _five_axis_result_with_error())

    assert len(gaps) == 1
    assert gaps[0].round_number == 1
    assert gaps[0].model == "qwen3.6-plus"
    assert gaps[0].reason == "error_output"


def test_five_axis_repair_recomputes_route_and_skip_final(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["jiaodafaxue-five"]
    result = _five_axis_result_with_error()
    gap = scan_five_axis_gaps(target, 99, result)[0]
    response = result["round1"]["models"]["deepseek-v4-pro"]

    repaired = merge_five_axis_response(
        result,
        gap,
        response,
        elapsed_seconds=1.2,
    )
    skipped = build_skip_round2(repaired)
    rebuilt = rebuild_five_axis_record(skipped)

    assert rebuilt["round2_mode"] == "skip"
    assert rebuilt["round2"]["skipped"] is True
    assert set(rebuilt["round1"]["models"]) == {
        "deepseek-v4-pro",
        "qwen3.6-plus",
    }
    assert rebuilt["final"]["per_model_total_scores"] == {
        "deepseek-v4-pro": 10,
        "qwen3.6-plus": 10,
    }


def test_five_axis_triggered_r2_requires_two_valid_models(tmp_path: Path) -> None:
    target = target_registry(tmp_path)["jiaodafaxue-five"]
    result = _five_axis_result_with_error()
    result["round2_mode"] = "full"
    result["round2"] = {
        "round2_mode": "full",
        "models": {"deepseek-v4-pro": result["round1"]["models"]["deepseek-v4-pro"]},
    }

    gaps = scan_five_axis_gaps(target, 99, result)

    assert {(gap.round_number, gap.model) for gap in gaps} == {
        (1, "qwen3.6-plus"),
        (2, "qwen3.6-plus"),
    }


def test_content_inspection_fallback_keeps_abstract_head_and_tail() -> None:
    paper = ProcessedPaper(
        abstract="摘要",
        introduction="引言" * 2_000,
        body="H" * 3_000 + "M" * 10_000 + "T" * 7_000,
        full_text="完整文本",
        structure_status="detected",
    )

    compact = compact_paper_for_content_inspection(paper)

    assert compact.abstract == "摘要"
    assert len(compact.introduction) == 2_000
    assert compact.body.startswith("H" * 3_000)
    assert compact.body.endswith("T" * 7_000)
    assert "中间论证已省略" in compact.body
