"""signal_check 模块测试：contradiction_triggers 四条规则 + 失败降级。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.evaluation.schemas import SignalCheckResult
from src.evaluation.signal_check import (
    _build_signal_result,
    check_contradiction_triggers,
    run_signal_check,
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
