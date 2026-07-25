import pytest

from src.knowledge.registry import load_model_set


def test_candidate_model_set_upgrades_only_targeted_six_dimension_models() -> None:
    production = load_model_set("six-dimension-v1")
    candidate = load_model_set("six-dimension-v2-candidate")

    assert production["status"] == "production"
    assert candidate["status"] == "candidate-unvalidated"
    assert candidate["provider_names"] == [
        "glm-5.2",
        "qwen3.7-max-2026-06-08",
        "deepseek-v4-pro",
        "kimi-k2.6",
    ]
    assert set(candidate["model_groups"]["lenient"]) | set(
        candidate["model_groups"]["strict"]
    ) == set(candidate["provider_names"])


def test_unknown_model_set_does_not_fall_back_silently() -> None:
    with pytest.raises(KeyError, match="未知模型集"):
        load_model_set("not-deployed")
