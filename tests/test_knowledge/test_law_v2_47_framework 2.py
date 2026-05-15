from pathlib import Path

import yaml

from src.knowledge.loader import load_framework


FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.47-20260511.yaml"
)


def load_framework_yaml() -> dict:
    return yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))


def forward_extension_prompt() -> str:
    framework = load_framework_yaml()
    dimension = next(
        item for item in framework["dimensions"] if item["key"] == "forward_extension"
    )
    return dimension["prompt_template"]


def test_v2_47_framework_loads_as_forward_extension_calibration_candidate():
    framework = load_framework(FRAMEWORK_PATH)

    assert framework.metadata.version == "2.47.0"
    assert "forward_extension" in framework.metadata.changelog
    assert len(framework.dimensions) == 6


def test_v2_47_forward_extension_uses_bonus_mapping_as_single_score_authority():
    prompt = forward_extension_prompt()

    assert "唯一计分口径" in prompt
    assert "原始分 >= 80 → bonus=5" in prompt
    assert "原始分 >= 60 → bonus=3" in prompt
    assert "原始分 >= 40 → bonus=2" in prompt
    assert "原始分 < 40 → bonus=0" in prompt
    assert "前瞻延展性不直接加权计入总分" in prompt


def test_v2_47_forward_extension_is_type_adaptive_without_full_future_design_requirement():
    prompt = forward_extension_prompt()

    assert "理论型论文：理论深化方向、概念修正路径、新理论假设" in prompt
    assert "判例/实务型论文：案例适用边界、实务改进路径、裁判规则延伸" in prompt
    assert "制度/立法型论文：制度完善方向、规则衔接问题、实施风险控制" in prompt
    assert "比较法论文：比较框架深化、新比较维度、本土化延伸" in prompt
    assert "不要求形成完整未来研究设计" in prompt


def test_v2_47_forward_extension_keeps_slogan_only_low_but_removes_old_low_anchors():
    prompt = forward_extension_prompt()

    assert "只有空泛拔高且没有具体待修正对象时，才进入0-39低分段" in prompt
    assert "延展实质度=1 且 正文衔接度≥3 → marginal(45-54)" not in prompt
    assert "延展实质度=2 且 正文衔接度≥3 → marginal(55-64)" not in prompt
    assert "触发weak_extension_path后，band只能是marginal或unacceptable" not in prompt
