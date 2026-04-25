from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.15-20260423.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_15_forward_extension_prompt_requires_concrete_next_step_for_high_scores():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "forward_extension")
    prompt = dimension["prompt_template"]

    assert "即使与正文衔接紧密，也通常最高65分" in prompt
    assert "具体后续问题、理论假设或概念修正路径" in prompt


def test_v2_15_conclusion_prompt_does_not_require_theory_papers_to_offer_institutional_path():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "conclusion_consensus")
    prompt = dimension["prompt_template"]

    assert "制度转化方向可作为加分项，不是理论论文达标前提" in prompt
    assert "不要因理论论文未给出未来制度转化方向而直接扣分" in prompt
