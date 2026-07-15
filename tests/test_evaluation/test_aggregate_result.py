"""aggregate_result 测试：输出字段完整性 + review_level 归类。"""

from __future__ import annotations

import pytest

from src.evaluation.precheck import PrecheckResult, _adapt_to_v014_contract
from src.evaluation.result_validator import (
    aggregate_result,
    aggregate_result_to_dict,
)
from src.evaluation.schemas import SignalCheckResult
from src.knowledge.loader import load_framework
from src.reliability.schemas import ReliabilityReport

FRAMEWORK_V2_45 = "configs/frameworks/law-v2.56.6-20260522.yaml"


@pytest.fixture
def framework():
    return load_framework(FRAMEWORK_V2_45)


@pytest.fixture
def dimension_scores():
    return {
        "problem_originality": 80,
        "literature_insight": 75,
        "analytical_framework": 70,
        "logical_coherence": 80,
        "conclusion_consensus": 80,
        "forward_extension": 70,
    }


@pytest.fixture
def reliability_reports():
    return [
        ReliabilityReport(
            dimension_key="problem_originality",
            mean=80, std=4, is_high_confidence=True, model_scores={"a": 80},
        ),
        ReliabilityReport(
            dimension_key="logical_coherence",
            mean=80, std=3, is_high_confidence=True, model_scores={"a": 80},
        ),
    ]


@pytest.fixture
def no_contradiction_signal():
    return SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="yes",
        external_theory_transformation="sufficient",
        verifiable_concept_or_thesis="yes",
        triggers_review=False,
    )


def test_contract_required_fields_present(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    """v0.14 §7.1 要求的 9 个 required fields 必须全部出现。"""
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    result = aggregate_result(
        dimension_scores,
        precheck,
        no_contradiction_signal,
        reliability_reports,
        framework,
    )

    required = [
        "precheck_conclusion",
        "base_score",
        "bonus_score",
        "conclusion_consensus_ceiling",
        "final_score",
        "multi_model_stats",
        "review_status",
        "review_level",
        "triage_recommendation",
    ]
    dumped = result.model_dump()
    for field in required:
        assert field in dumped, f"missing required field: {field}"


def test_precheck_conclusion_transparent_pass(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    """pass → enter_six_dimension_review → review_level=none."""
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    result = aggregate_result(
        dimension_scores, precheck, no_contradiction_signal,
        reliability_reports, framework,
    )
    assert result.precheck_conclusion == "enter_six_dimension_review"
    assert result.review_status == "none"
    assert result.review_level == "none"
    assert result.triage_recommendation == "enter_six_dim"


def test_boundary_review_triggers_precheck_level(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    """manual_review → boundary_review → review_level=precheck_level."""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="manual_review", issues=["信号弱"]), framework
    )
    result = aggregate_result(
        dimension_scores, precheck, no_contradiction_signal,
        reliability_reports, framework,
    )
    assert result.precheck_conclusion == "boundary_review"
    assert result.review_status == "required"
    assert result.review_level == "precheck_level"
    assert result.triage_recommendation == "boundary_with_review"


def test_contradiction_triggers_evaluation_level(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    """预检通过但矛盾规则触发 → review_level=evaluation_level."""
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    result = aggregate_result(
        dimension_scores, precheck, no_contradiction_signal,
        reliability_reports, framework,
        contradiction_rules=["total_high_but_no_china_problem"],
    )
    assert result.review_status == "required"
    assert result.review_level == "evaluation_level"
    assert result.triggered_rules == ["total_high_but_no_china_problem"]


def test_multi_model_stats_computed_from_reports(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    result = aggregate_result(
        dimension_scores, precheck, no_contradiction_signal,
        reliability_reports, framework,
    )
    assert result.multi_model_stats is not None
    # reliability 都是 std=3,4 → 平均 3.5 < std_threshold 5.0 → high confidence
    assert result.multi_model_stats.confidence_label == "high"


def test_aggregate_result_to_dict_serializable(
    framework, dimension_scores, reliability_reports, no_contradiction_signal
):
    """序列化结果可以写入 papers.aggregate_result JSON 字段。"""
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    result = aggregate_result(
        dimension_scores, precheck, no_contradiction_signal,
        reliability_reports, framework,
    )
    d = aggregate_result_to_dict(result)
    assert isinstance(d, dict)
    assert d["precheck_conclusion"] == "enter_six_dimension_review"
    assert isinstance(d["final_score"], float)
    # multi_model_stats 应被展开为 dict
    assert isinstance(d["multi_model_stats"], dict)


def test_legacy_framework_no_scoring_protocol_gracefully_handled(
    no_contradiction_signal, reliability_reports
):
    """旧框架无 scoring_protocol 时，base/bonus/ceiling 都应为 0/None 而非崩溃。"""
    current = load_framework(FRAMEWORK_V2_45)
    raw_config = dict(current.raw_config)
    raw_config.pop("scoring_protocol", None)
    fw = current.model_copy(update={"raw_config": raw_config})
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), fw)
    result = aggregate_result(
        {"problem_originality": 80, "literature_insight": 70},
        precheck, no_contradiction_signal, reliability_reports, fw,
    )
    # 无 scoring_protocol → base=0, bonus=0, ceiling=None, final=0
    assert result.base_score == 0.0
    assert result.bonus_score == 0.0
    assert result.conclusion_consensus_ceiling is None
    assert result.final_score == 0.0
    # precheck_conclusion 取默认值（旧框架不走适配层）
    assert result.precheck_conclusion == "enter_six_dimension_review"
