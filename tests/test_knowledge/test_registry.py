from pathlib import Path

from src.knowledge.registry import (
    DEFAULT_FRAMEWORK_ROLE,
    assert_embedded_scoring_protocols_match,
    load_position_framework,
    load_review_protocol,
    load_scoring_protocol,
    resolve_framework_path,
)


def test_registry_resolves_active_default_framework():
    path = resolve_framework_path(DEFAULT_FRAMEWORK_ROLE)

    assert path.name == "law-v2.56.6-20260522.yaml"
    assert path.is_file()


def test_registry_loads_canonical_ccb_protocol():
    protocol = load_scoring_protocol()

    assert protocol["mode"] == "core_ceiling_bonus"
    assert protocol["total_max"] == 100
    assert Path(protocol["source_path"]).name == "core-ceiling-bonus-v0.8.yaml"


def test_registry_loads_validated_position_and_cross_review_protocols():
    position = load_position_framework()
    review = load_review_protocol()

    assert [axis["key"] for axis in position["axes"]] == [
        "object_belonging",
        "material_belonging",
        "category_autonomy",
        "explanatory_orientation",
        "system_mappability",
    ]
    assert review["model_groups"]["lenient"] == ["glm-5.1", "qwen3.6-plus"]
    assert review["unresolved_disagreement"] == {
        "std_threshold": 8,
        "action": "expert_review",
    }


def test_all_embedded_ccb_protocols_match_canonical_truth():
    assert assert_embedded_scoring_protocols_match() == []
