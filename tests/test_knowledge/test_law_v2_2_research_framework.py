from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.2-20260421.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_2_framework_file_exists():
    assert FRAMEWORK_PATH.exists()


def test_v2_2_keeps_six_dimensions_and_weights():
    framework = load_framework()
    dimensions = framework["dimensions"]

    assert len(dimensions) == 6
    assert sum(d["weight"] for d in dimensions) == 1.0
    assert [d["key"] for d in dimensions] == [
        "problem_originality",
        "literature_insight",
        "analytical_framework",
        "logical_coherence",
        "conclusion_consensus",
        "forward_extension",
    ]


def test_v2_2_renames_conclusion_dimension_for_display():
    framework = load_framework()
    conclusion_dimension = next(
        d for d in framework["dimensions"] if d["key"] == "conclusion_consensus"
    )

    assert conclusion_dimension["name_zh"] == "结论可接受性"


def test_v2_2_precheck_uses_manual_review_for_ethics_risk():
    framework = load_framework()
    precheck = framework["precheck"]
    ethics_criterion = next(c for c in precheck["criteria"] if c["key"] == "academic_ethics")

    assert "疑点筛查" in ethics_criterion["description"]
    assert "manual_review" in precheck["prompt_template"]
    assert '"status": "pass|conditional_pass|manual_review"' in precheck["prompt_template"]


def test_v2_2_dimension_prompts_drop_model_self_reported_confidence():
    framework = load_framework()

    for dimension in framework["dimensions"]:
        prompt = dimension["prompt_template"]
        assert '"confidence"' not in prompt
        assert '"review_flags"' in prompt


def test_v2_2_moves_governance_rules_into_appendix():
    framework = load_framework()

    assert "governance_appendix" in framework
    appendix = framework["governance_appendix"]
    assert "expert_review_triggers" in appendix
    assert "validation_plan" in appendix
    assert "reliability_verification" in appendix
