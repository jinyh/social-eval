from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.30-20260425.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_30_uses_core_ceiling_bonus_protocol():
    framework = load_framework()
    protocol = framework["scoring_protocol"]

    assert protocol["mode"] == "core_ceiling_bonus"
    assert protocol["ceiling_dimension"]["key"] == "conclusion_consensus"
    assert protocol["bonus_dimension"]["key"] == "forward_extension"


def test_v2_30_core_weights_match_v0_7():
    framework = load_framework()
    dimensions = {item["key"]: item["weight"] for item in framework["dimensions"]}

    assert dimensions["problem_originality"] == 0.30
    assert dimensions["literature_insight"] == 0.20
    assert dimensions["analytical_framework"] == 0.15
    assert dimensions["logical_coherence"] == 0.20
    assert sum(dimensions.values()) == 1.0


def test_v2_30_logical_coherence_uses_sufficiency_wording():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "logical_coherence")

    assert "充分支撑链条" in dimension["description"]
    assert "可辩护地推出" in dimension["description"]
