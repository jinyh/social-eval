"""v2.46/v0.16 pipeline tests for low-leakage large-scale screening."""

from __future__ import annotations

from pathlib import Path

from src.evaluation.prompt_builder import build_precheck_prompt, build_signal_check_prompt
from src.evaluation.precheck import PrecheckResult, _adapt_to_v014_contract
from src.evaluation.result_validator import aggregate_result
from src.evaluation.schemas import SignalCheckResult
from src.evaluation.signal_check import _build_signal_result
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.loader import load_framework

FRAMEWORK_V2_46 = (
    "configs/frameworks/archive/v2.0-v2.54-20260522/law-v2.46-20260511.yaml"
)


def test_v2_46_precheck_prompt_keeps_project_scope_as_stage_one():
    framework = load_framework(FRAMEWORK_V2_46)
    paper = ProcessedPaper(
        body="论文正文",
        full_text="论文全文",
        references=[],
        structure_status="detected",
    )

    prompt = build_precheck_prompt(framework, paper)

    assert "【阶段1：项目口径预检】" in prompt
    assert "text_quality_gate 只是旁路工程字段" in prompt
    assert prompt.index("【主任务：project_scope_precheck】") < prompt.index(
        "【旁路字段：text_quality_gate】"
    )


def test_v2_46_signal_prompt_comes_from_framework_yaml():
    framework = load_framework(FRAMEWORK_V2_46)
    signal_config = framework.raw_config["autonomous_knowledge_signals"]
    paper = ProcessedPaper(
        body="论文正文",
        full_text="论文全文",
        references=[],
        structure_status="detected",
    )

    assert signal_config["prompt_template"]
    assert signal_config["output_template"]

    prompt = build_signal_check_prompt(framework, paper)

    assert "【阶段3：自主知识体系信号校验】" in prompt
    assert "v0.16 YAML 配置版" in prompt
    assert '"autonomous_signal_score": 0-8' in prompt
    assert "论文正文：\n论文正文" in prompt


def test_v0_16_doc_points_prompt_details_to_v2_46_yaml():
    doc = Path(
        "docs/evaluation/archive/v0.1-v0.15-iterations-20260601/"
        "law-ai-assisted-review-rules-v0.16-large-scale-candidate.md"
    ).read_text(encoding="utf-8")

    assert "六维评分的精确字段、字数限制、prompt 与 JSON 契约" in doc
    assert (
        "configs/frameworks/archive/v2.0-v2.54-20260522/law-v2.46-20260511.yaml"
        in doc
    )


def test_v2_46_precheck_separates_text_quality_from_project_scope():
    framework = load_framework(FRAMEWORK_V2_46)

    precheck = PrecheckResult(
        status="conditional_pass",
        conclusion="enter_six_dimension_review",
        enter_six_dimension_review="yes",
        text_quality_gate={
            "status": "risk",
            "risk_level": "medium",
            "issues": ["脚注编号乱码，但正文论点可定位"],
        },
        project_scope_precheck={
            "conclusion": "enter_six_dimension_review",
            "triggered_signals": {
                "involves_china_issues": "yes",
                "has_legal_question": "yes",
                "china_practice_explanation_attempted": "yes",
                "theory_transformation_or_verifiable_thesis": "yes",
            },
        },
    )

    adapted = _adapt_to_v014_contract(precheck, framework)

    assert adapted.conclusion == "enter_six_dimension_review"
    assert adapted.enter_six_dimension_review == "yes"
    assert adapted.requires_manual_confirmation is False
    assert adapted.text_quality_gate is not None
    assert adapted.text_quality_gate["status"] == "risk"


def test_v2_46_signal_quantification_is_available_without_direct_scoring():
    signal = _build_signal_result(
        {
            "china_problem_centered": "yes",
            "china_practice_explanation_attempted": "partial",
            "external_theory_transformation": "sufficient",
            "verifiable_concept_or_thesis": "yes",
            "evidence_quotes": ["证据"],
            "risks": ["china_material_as_background_only"],
            "triggers_review": False,
        }
    )

    assert signal.autonomous_signal_score == 7
    assert signal.autonomous_signal_strength == "strong"
    assert signal.signal_scores == {
        "china_problem_centered": 2,
        "china_practice_explanation_attempted": 1,
        "external_theory_transformation": 2,
        "verifiable_concept_or_thesis": 2,
    }


def test_v2_46_aggregate_exposes_signal_score_and_recommends_risk_review():
    framework = load_framework(FRAMEWORK_V2_46)
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework)
    signal = SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="yes",
        external_theory_transformation="sufficient",
        verifiable_concept_or_thesis="yes",
        autonomous_signal_score=8,
        autonomous_signal_strength="strong",
        risks=["slogan_inflation_without_legal_argument"],
    )

    result = aggregate_result(
        {
            "problem_originality": 86,
            "literature_insight": 82,
            "analytical_framework": 84,
            "logical_coherence": 84,
            "conclusion_consensus": 82,
            "forward_extension": 45,
        },
        precheck,
        signal,
        [],
        framework,
    )

    assert result.autonomous_signal_score == 8
    assert result.autonomous_signal_strength == "strong"
    assert result.review_status == "recommended"
    assert result.review_level == "evaluation_level"
    assert "high_score_with_autonomous_signal_risk" in result.triggered_rules
