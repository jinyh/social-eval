"""signal_check 模块测试：contradiction_triggers 四条规则 + 失败降级。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.evaluation.schemas import SignalCheckResult
from src.evaluation.signal_check import (
    _build_signal_result,
    aggregate_signal_results,
    check_contradiction_triggers,
    run_signal_check,
    run_signal_check_multi,
)
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.loader import load_framework
from src.reliability.schemas import ReliabilityReport

FRAMEWORK_V2_45 = "configs/frameworks/law-v2.45-20260510.yaml"
FRAMEWORK_V2_0 = "configs/frameworks/law-v2.0-20260413.yaml"


@pytest.fixture
def framework_v2_45():
    return load_framework(FRAMEWORK_V2_45)


@pytest.fixture
def framework_legacy():
    return load_framework(FRAMEWORK_V2_0)


@pytest.fixture
def paper():
    return ProcessedPaper(
        body="这是正文内容。",
        full_text="这是正文内容。",
        references=["参考文献1"],
        structure_status="complete",
    )


def test_build_signal_result_populates_flat_and_legacy_fields():
    """_build_signal_result 同时填充扁平四信号字段与 legacy signals 列表。"""
    payload = {
        "china_problem_centered": "yes",
        "china_practice_explanation_attempted": "partial",
        "external_theory_transformation": "sufficient",
        "verifiable_concept_or_thesis": "yes",
        "evidence_quotes": ["证据1"],
        "risks": [],
        "triggers_review": False,
    }
    result = _build_signal_result(payload)
    assert result.china_problem_centered == "yes"
    assert result.china_practice_explanation_attempted == "partial"
    # legacy signals 列表
    assert len(result.signals) == 4
    keys = [s.signal_key for s in result.signals]
    assert "china_problem_centered" in keys


def test_rule_1_total_high_but_no_china_problem(framework_v2_45):
    signal = SignalCheckResult(china_problem_centered="no")
    reports = [
        ReliabilityReport(
            dimension_key="problem_originality",
            mean=60, std=3, is_high_confidence=True, model_scores={},
        )
    ]
    triggered, rules = check_contradiction_triggers(signal, reports, framework_v2_45, 75)
    assert triggered
    assert "total_high_but_no_china_problem" in rules


def test_rule_2_total_low_but_all_signals_yes(framework_v2_45):
    signal = SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="yes",
        external_theory_transformation="sufficient",
        verifiable_concept_or_thesis="yes",
    )
    triggered, rules = check_contradiction_triggers(signal, [], framework_v2_45, 45)
    assert triggered
    assert "total_low_but_all_signals_yes" in rules


def test_rule_3_high_originality_but_no_verifiable_thesis(framework_v2_45):
    signal = SignalCheckResult(verifiable_concept_or_thesis="no")
    reports = [
        ReliabilityReport(
            dimension_key="problem_originality",
            mean=85, std=3, is_high_confidence=True, model_scores={},
        )
    ]
    triggered, rules = check_contradiction_triggers(signal, reports, framework_v2_45, 72)
    assert triggered
    assert "high_originality_but_no_verifiable_thesis" in rules


def test_rule_4_self_reported_trigger(framework_v2_45):
    """signal 自身声明 triggers_review=True 应透传到 triggered rules。"""
    signal = SignalCheckResult(
        triggers_review=True,
        review_reason="slogan_heavy_but_no_legal_question",
    )
    triggered, rules = check_contradiction_triggers(signal, [], framework_v2_45, 60)
    assert triggered
    assert "slogan_heavy_but_no_legal_question" in rules


def test_no_trigger_when_balanced(framework_v2_45):
    signal = SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="partial",
        external_theory_transformation="partial",
        verifiable_concept_or_thesis="yes",
    )
    reports = [
        ReliabilityReport(
            dimension_key="problem_originality",
            mean=70, std=3, is_high_confidence=True, model_scores={},
        )
    ]
    triggered, rules = check_contradiction_triggers(signal, reports, framework_v2_45, 70)
    assert not triggered
    assert rules == []


def test_legacy_framework_never_triggers(framework_legacy):
    """旧框架（无 autonomous_knowledge_signals）永不触发规则。"""
    signal = SignalCheckResult(china_problem_centered="no")
    triggered, rules = check_contradiction_triggers(signal, [], framework_legacy, 85)
    assert not triggered
    assert rules == []


@pytest.mark.asyncio
async def test_run_signal_check_graceful_failure(framework_v2_45, paper):
    """signal_check 异常时不抛出，返回 triggers_review=True 的降级结果。"""

    class FailingProvider:
        model_name = "test-fail"

        async def generate_json_response(self, prompt):
            raise RuntimeError("simulated API failure")

    result = await run_signal_check(
        FailingProvider(), framework_v2_45, paper, task_id="t1", db=None
    )
    assert result.triggers_review
    assert "signal_check_failed" in (result.review_reason or "")


@pytest.mark.asyncio
async def test_run_signal_check_success(framework_v2_45, paper):
    """signal_check 成功时返回扁平信号字段。"""
    provider = AsyncMock()
    provider.model_name = "test-ok"
    provider.generate_json_response = AsyncMock(
        return_value={
            "china_problem_centered": "yes",
            "china_practice_explanation_attempted": "yes",
            "external_theory_transformation": "sufficient",
            "verifiable_concept_or_thesis": "yes",
            "evidence_quotes": ["证据"],
            "risks": [],
            "triggers_review": False,
        }
    )
    result = await run_signal_check(
        provider, framework_v2_45, paper, task_id="t2", db=None
    )
    assert result.china_problem_centered == "yes"
    assert not result.triggers_review


# === 多模型聚合测试 ===


def test_aggregate_signal_results_takes_max():
    """激进聚合：每项 signal_score 取 max。"""
    r1 = SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="no",
        external_theory_transformation="no",
        verifiable_concept_or_thesis="partial",
        signal_scores={
            "china_problem_centered": 2,
            "china_practice_explanation_attempted": 0,
            "external_theory_transformation": 0,
            "verifiable_concept_or_thesis": 1,
        },
        autonomous_signal_score=3,
        autonomous_signal_strength="weak",
        evidence_quotes=["证据A"],
    )
    r2 = SignalCheckResult(
        china_problem_centered="partial",
        china_practice_explanation_attempted="yes",
        external_theory_transformation="sufficient",
        verifiable_concept_or_thesis="yes",
        signal_scores={
            "china_problem_centered": 1,
            "china_practice_explanation_attempted": 2,
            "external_theory_transformation": 2,
            "verifiable_concept_or_thesis": 2,
        },
        autonomous_signal_score=7,
        autonomous_signal_strength="strong",
        evidence_quotes=["证据B"],
    )
    result = aggregate_signal_results([r1, r2], ["glm", "qwen"])

    assert result.signal_scores["china_problem_centered"] == 2
    assert result.signal_scores["china_practice_explanation_attempted"] == 2
    assert result.signal_scores["external_theory_transformation"] == 2
    assert result.signal_scores["verifiable_concept_or_thesis"] == 2
    assert result.autonomous_signal_score == 8
    assert result.autonomous_signal_strength == "strong"
    # 取 max 的模型判断值
    assert result.china_problem_centered == "yes"  # r1 score=2 > r2 score=1
    assert result.china_practice_explanation_attempted == "yes"  # r2 score=2 > r1 score=0


def test_aggregate_signal_results_agreement_true():
    """两模型完全一致时 agreement=True。"""
    scores = {
        "china_problem_centered": 2,
        "china_practice_explanation_attempted": 1,
        "external_theory_transformation": 0,
        "verifiable_concept_or_thesis": 2,
    }
    r1 = SignalCheckResult(signal_scores=dict(scores), autonomous_signal_score=5)
    r2 = SignalCheckResult(signal_scores=dict(scores), autonomous_signal_score=5)
    result = aggregate_signal_results([r1, r2])
    assert result.signal_model_agreement is True


def test_aggregate_signal_results_agreement_false():
    """任一项不同时 agreement=False。"""
    r1 = SignalCheckResult(
        signal_scores={
            "china_problem_centered": 2,
            "china_practice_explanation_attempted": 1,
            "external_theory_transformation": 0,
            "verifiable_concept_or_thesis": 2,
        },
    )
    r2 = SignalCheckResult(
        signal_scores={
            "china_problem_centered": 2,
            "china_practice_explanation_attempted": 0,  # 不同
            "external_theory_transformation": 0,
            "verifiable_concept_or_thesis": 2,
        },
    )
    result = aggregate_signal_results([r1, r2])
    assert result.signal_model_agreement is False


def test_aggregate_signal_results_single_model():
    """单模型时直接返回，agreement=True。"""
    r = SignalCheckResult(
        signal_scores={"china_problem_centered": 2, "china_practice_explanation_attempted": 1,
                       "external_theory_transformation": 0, "verifiable_concept_or_thesis": 2},
        autonomous_signal_score=5,
    )
    result = aggregate_signal_results([r])
    assert result.signal_model_agreement is True
    assert result is r


def test_aggregate_signal_results_empty():
    """空列表降级为 triggers_review=True。"""
    result = aggregate_signal_results([])
    assert result.triggers_review is True
    assert "all providers failed" in (result.review_reason or "")


def test_aggregate_signal_results_evidence_dedup():
    """evidence_quotes 合并去重。"""
    r1 = SignalCheckResult(
        signal_scores={"china_problem_centered": 1, "china_practice_explanation_attempted": 0,
                       "external_theory_transformation": 0, "verifiable_concept_or_thesis": 0},
        evidence_quotes=["证据A", "证据B"],
    )
    r2 = SignalCheckResult(
        signal_scores={"china_problem_centered": 1, "china_practice_explanation_attempted": 0,
                       "external_theory_transformation": 0, "verifiable_concept_or_thesis": 0},
        evidence_quotes=["证据B", "证据C"],
    )
    result = aggregate_signal_results([r1, r2])
    assert result.evidence_quotes == ["证据A", "证据B", "证据C"]


def test_aggregate_signal_results_triggers_review_or():
    """任一模型 triggers_review=True 则聚合结果也触发。"""
    r1 = SignalCheckResult(
        signal_scores={"china_problem_centered": 2, "china_practice_explanation_attempted": 2,
                       "external_theory_transformation": 2, "verifiable_concept_or_thesis": 2},
        triggers_review=False,
    )
    r2 = SignalCheckResult(
        signal_scores={"china_problem_centered": 2, "china_practice_explanation_attempted": 2,
                       "external_theory_transformation": 2, "verifiable_concept_or_thesis": 2},
        triggers_review=True,
        review_reason="slogan_heavy_but_no_legal_question",
    )
    result = aggregate_signal_results([r1, r2])
    assert result.triggers_review is True
    assert "slogan_heavy_but_no_legal_question" in result.review_reason


def test_aggregate_signal_results_per_model_scores():
    """per_model_signal_scores 记录各模型原始分。"""
    r1 = SignalCheckResult(
        signal_scores={"china_problem_centered": 2, "china_practice_explanation_attempted": 0,
                       "external_theory_transformation": 1, "verifiable_concept_or_thesis": 2},
    )
    r2 = SignalCheckResult(
        signal_scores={"china_problem_centered": 1, "china_practice_explanation_attempted": 2,
                       "external_theory_transformation": 0, "verifiable_concept_or_thesis": 1},
    )
    result = aggregate_signal_results([r1, r2], ["glm-5.1", "qwen3.6-plus"])
    assert result.per_model_signal_scores["glm-5.1"]["china_problem_centered"] == 2
    assert result.per_model_signal_scores["qwen3.6-plus"]["china_practice_explanation_attempted"] == 2


@pytest.mark.asyncio
async def test_run_signal_check_multi_filters_failures(framework_v2_45, paper):
    """多模型并发时，过滤掉失败降级的结果。"""

    class OkProvider:
        model_name = "ok-model"

        async def generate_json_response(self, prompt):
            return {
                "china_problem_centered": "yes",
                "china_practice_explanation_attempted": "yes",
                "external_theory_transformation": "sufficient",
                "verifiable_concept_or_thesis": "yes",
                "evidence_quotes": ["证据"],
                "risks": [],
                "triggers_review": False,
            }

    class FailProvider:
        model_name = "fail-model"

        async def generate_json_response(self, prompt):
            raise RuntimeError("simulated failure")

    results = await run_signal_check_multi(
        [OkProvider(), FailProvider()], framework_v2_45, paper, "t3", db=None
    )
    # 只保留成功的结果
    assert len(results) == 1
    assert results[0].china_problem_centered == "yes"
