from pathlib import Path

import yaml


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.17-20260424.yaml"
)


def load_framework() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def test_v2_17_forward_extension_prompt_distinguishes_slogan_only_from_targeted_revision_direction():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "forward_extension")
    prompt = dimension["prompt_template"]

    assert "只有“值得进一步研究”“继续努力完善”等空泛表述，且未指明具体待修正对象时，才记为延展实质度=0" in prompt
    assert "若论文已明确指出正文中的具体局限，并说明后续应围绕该局限继续修正/完善，即可计入延展实质度=1" in prompt


def test_v2_17_forward_extension_prompt_keeps_weak_extension_path_in_marginal_band():
    framework = load_framework()
    dimension = next(d for d in framework["dimensions"] if d["key"] == "forward_extension")
    prompt = dimension["prompt_template"]

    assert "延展实质度=1 且 正文衔接度≥3 → marginal(45-54)" in prompt
    assert "延展实质度=2 且 正文衔接度≥3 → marginal(55-64)" in prompt
    assert "触发weak_extension_path后，band只能是marginal或unacceptable" in prompt
