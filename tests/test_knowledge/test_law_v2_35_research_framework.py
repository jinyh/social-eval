from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.35-20260425.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def dimension(framework: dict, key: str) -> dict:
    return next(item for item in framework["dimensions"] if item["key"] == key)


def test_v2_35_metadata_skips_v2_34_and_bases_on_v2_33():
    framework = load_framework()

    assert framework["metadata"]["version"] == "2.35.0"
    assert framework["metadata"]["previous_version"] == "2.33.0"
    assert "跳过 v2.34" in framework["metadata"]["changelog"]


def test_v2_35_keeps_v0_8_core_ceiling_bonus_protocol():
    framework = load_framework()
    protocol = framework["scoring_protocol"]

    assert protocol["mode"] == "core_ceiling_bonus"
    assert protocol["ceiling_dimension"]["key"] == "conclusion_consensus"
    assert protocol["bonus_dimension"]["key"] == "forward_extension"
    assert "AI 只做初筛" in framework["scoring_structure"]["description"]


def test_v2_35_demotes_material_novelty_as_originality_signal():
    framework = load_framework()
    originality = dimension(framework, "problem_originality")

    rule_ids = {rule["rule_id"] for rule in originality["ceiling_rules"]}
    assert "problem_originality.material_novelty_without_thesis" in rule_ids
    assert "材料创新降权" in framework["metadata"]["changelog"]
    assert "不能单独支撑高创新性" in originality["prompt_template"]
    assert "material_novelty_overclaim" in originality["prompt_template"]


def test_v2_35_literature_insight_uses_internal_evidence_by_default():
    framework = load_framework()
    literature = dimension(framework, "literature_insight")

    assert "默认采用“文内证据模式”" in literature["prompt_template"]
    assert "外部文献库/RAG 增强模式" in literature["prompt_template"]
    assert "外部文献不得替代文内证据直接给高分或低分" in literature["prompt_template"]
    assert "external_context_conflict" in literature["prompt_template"]


def test_v2_35_logical_coherence_uses_defensible_support_wording():
    framework = load_framework()
    logical = dimension(framework, "logical_coherence")

    assert "充分支撑链条" in logical["description"]
    assert "可辩护地推出" in logical["description"]
    assert "不要把\"必要推出\"作为硬标准" in logical["prompt_template"]


def test_v2_35_requires_expert_review_for_high_innovation_low_acceptability():
    framework = load_framework()
    triggers = framework["expert_review_triggers"]["overall_triggers"]

    assert any(
        "研究创新性>=80" in trigger["condition"]
        and "结论可接受性<60" in trigger["condition"]
        for trigger in triggers
    )
