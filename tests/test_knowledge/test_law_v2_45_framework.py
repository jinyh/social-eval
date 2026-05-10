"""v2.45 法学评价框架测试：验证全链路对齐。

- YAML 可加载，新字段全部可通过 Framework 属性访问
- 三份契约（signal/aggregate/review_report）同时可通过 raw_config 访问（兼容）
- 六维 prompt_template 与 v2.44 字节级一致（评分不回归）
"""

from __future__ import annotations

import hashlib

import yaml

from src.knowledge.contract_helpers import (
    get_aggregate_contract,
    get_contradiction_triggers,
    get_review_report_contract,
    get_scoring_protocol,
    get_signal_config,
    is_full_pipeline_framework,
)
from src.knowledge.loader import load_framework

V2_44_PATH = "configs/frameworks/law-v2.44-20260508.yaml"
V2_45_PATH = "configs/frameworks/law-v2.45-20260510.yaml"


def test_v2_45_loads_with_contract_fields():
    fw = load_framework(V2_45_PATH)
    assert fw.version == "2.45.0"
    assert fw.discipline == "法学"
    assert len(fw.dimensions) == 6

    # 三份契约通过 Framework 显式字段访问
    assert fw.autonomous_knowledge_signals is not None
    assert fw.aggregate_output_contract is not None
    assert fw.review_report is not None

    # scoring_protocol 仍在 raw_config（v2.45 未升为 Framework 字段）
    assert fw.raw_config.get("scoring_protocol") is not None


def test_v2_45_contract_helpers():
    fw = load_framework(V2_45_PATH)
    assert get_signal_config(fw) is not None
    assert get_aggregate_contract(fw) is not None
    assert get_review_report_contract(fw) is not None
    assert get_scoring_protocol(fw) is not None
    assert is_full_pipeline_framework(fw)

    # 四条 contradiction_triggers（对应 v0.14 §6.1.2）
    triggers = get_contradiction_triggers(fw)
    assert len(triggers) == 4
    rule_ids = [t["rule"] for t in triggers]
    assert "total_high_but_no_china_problem" in rule_ids
    assert "total_low_but_all_signals_yes" in rule_ids
    assert "high_originality_but_no_verifiable_thesis" in rule_ids


def test_v2_45_six_dimension_prompts_identical_to_v2_44():
    """v2.45 六维 prompt_template 必须与 v2.44 字节级一致，保证评分不回归。"""
    cfg_44 = yaml.safe_load(open(V2_44_PATH, encoding="utf-8"))
    cfg_45 = yaml.safe_load(open(V2_45_PATH, encoding="utf-8"))

    dims_44 = {d["key"]: d for d in cfg_44["dimensions"]}
    dims_45 = {d["key"]: d for d in cfg_45["dimensions"]}

    assert set(dims_44.keys()) == set(dims_45.keys())

    for key in dims_44:
        p44 = dims_44[key]["prompt_template"]
        p45 = dims_45[key]["prompt_template"]
        h44 = hashlib.sha256(p44.encode("utf-8")).hexdigest()
        h45 = hashlib.sha256(p45.encode("utf-8")).hexdigest()
        assert h44 == h45, f"dimension {key}: v2.45 prompt 与 v2.44 不一致"


def test_v2_45_precheck_prompt_identical_to_v2_44():
    """precheck prompt 也须字节级一致（保持原有预检行为）。"""
    cfg_44 = yaml.safe_load(open(V2_44_PATH, encoding="utf-8"))
    cfg_45 = yaml.safe_load(open(V2_45_PATH, encoding="utf-8"))
    assert cfg_44["precheck"]["prompt_template"] == cfg_45["precheck"]["prompt_template"]


def test_legacy_framework_still_loads_without_new_fields():
    """v2.0 等老框架仍可加载，新字段为 None（向后兼容）。"""
    fw = load_framework("configs/frameworks/law-v2.0-20260413.yaml")
    assert fw.autonomous_knowledge_signals is None
    assert fw.aggregate_output_contract is None
    assert fw.review_report is None
    assert not is_full_pipeline_framework(fw)
