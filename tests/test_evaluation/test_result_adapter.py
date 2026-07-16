from pathlib import Path

from src.evaluation.result_adapter import normalize_six_dimension_result


def test_adapter_normalizes_legacy_r1_and_uses_ccb_as_primary_score(tmp_path: Path):
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    actual = raw_root / "002_示例论文 2.pdf"
    actual.write_bytes(b"pdf")
    payload = {
        "paper": "raw/002_示例论文.pdf",
        "framework": "configs/frameworks/law-v2.55-cross-review.yaml",
        "dimensions": {
            "problem_originality": {"model_scores": {"a": 80, "b": 90}},
            "literature_insight": {"model_scores": {"a": 80, "b": 80}},
            "analytical_framework": {"model_scores": {"a": 80, "b": 80}},
            "logical_coherence": {"model_scores": {"a": 80, "b": 80}},
            "conclusion_consensus": {"model_scores": {"a": 80, "b": 80}},
            "forward_extension": {"model_scores": {"a": 40, "b": 40}},
        },
        "overall": {"round2_final_score_mean": 73.33},
    }

    normalized = normalize_six_dimension_result(
        payload,
        paper_id=2,
        raw_root=raw_root,
    )

    assert normalized.dimensions["problem_originality"].round1_scores == {
        "a": 80.0,
        "b": 90.0,
    }
    assert normalized.dimensions["problem_originality"].round2_scores == {}
    assert normalized.stored_paper_path == "raw/002_示例论文.pdf"
    assert normalized.resolved_paper_path == actual
    assert normalized.round2_simple_mean == 73.33
    assert normalized.ccb_score == 83.76


def test_adapter_keeps_missing_historical_raw_responses_explicit():
    payload = {
        "paper": "paper.pdf",
        "dimensions": {
            "problem_originality": {
                "round1_scores": {"a": 80},
                "round2_scores": {"a": 82},
                "raw_outputs": {"a": {"score": 80}},
            }
        },
    }

    normalized = normalize_six_dimension_result(payload, paper_id=1)

    dimension = normalized.dimensions["problem_originality"]
    assert dimension.round1_raw_available == {"a": True}
    assert dimension.round2_raw_available == {"a": False}
