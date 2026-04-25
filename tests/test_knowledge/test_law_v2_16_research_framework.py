from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.16-20260424.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_16_forward_extension_prompt_hardens_low_score_anchor_mapping():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "forward_extension")
    prompt = dimension["prompt_template"]

    assert "延展实质度=1 且 正文衔接度≥3 → marginal(45-54)" in prompt
    assert "延展实质度=2 且 正文衔接度≥3 → marginal(55-64)" in prompt
    assert "延展实质度=0 → unacceptable(0-39)" in prompt


def test_v2_16_forward_extension_prompt_forbids_good_band_after_weak_extension_rule():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "forward_extension")
    prompt = dimension["prompt_template"]

    assert "触发weak_extension_path后，band只能是marginal或unacceptable" in prompt
    assert "不得因正文衔接高而进入good或excellent" in prompt
