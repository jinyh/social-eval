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

    assert position["metadata"]["version"] == "0.3"
    assert Path(position["source_path"]).name == "law-position-v0.3.yaml"
    assert [axis["key"] for axis in position["axes"]] == [
        "object_belonging",
        "material_belonging",
        "category_autonomy",
        "explanatory_orientation",
        "system_mappability",
    ]
    assert [
        (axis["name_zh"], axis["focus_zh"], axis["question_zh"])
        for axis in position["axes"]
    ] == [
        ("对象归属度", "研究问题归属", "核心问题是否归属于中国法学语境"),
        (
            "材料归属度",
            "核心材料归属",
            "材料是否来自中国规范、判例、史料、数据",
        ),
        ("范畴自主度", "分析范畴自主", "核心范畴是否经中国法语境重置"),
        (
            "解释目标归属度",
            "解释目标方向",
            "最终目标是否指向中国法学知识生产",
        ),
        ("体系映射度", "知识体系映射", "知识能否映射到知识树位置"),
    ]
    assert position["models"] == [
        "deepseek-v4-pro",
        "qwen3.7-max-2026-06-08",
    ]
    assert review["model_groups"]["lenient"] == ["glm-5.1", "qwen3.6-plus"]
    assert review["unresolved_disagreement"] == {
        "std_threshold": 8,
        "action": "expert_review",
    }

    peer_review = load_review_protocol("six_dimension_peer_review")
    assert peer_review["review_mode"] == "all_peers"
    assert peer_review["execution"]["require_complete_first_round"] is True
    assert peer_review["execution"]["anonymize_peer_identity"] is True


def test_all_embedded_ccb_protocols_match_canonical_truth():
    assert assert_embedded_scoring_protocols_match() == []
