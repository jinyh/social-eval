import pytest

from src.core.exceptions import EvaluationError
from src.evaluation.schemas import DimensionResult, LimitRuleTriggered
from src.knowledge.loader import load_framework


def _load_dimension(key: str):
    framework = load_framework("configs/frameworks/law-v2.15-20260423.yaml")
    return next(dimension for dimension in framework.dimensions if dimension.key == key)


def test_normalize_dimension_result_caps_score_to_lowest_triggered_ceiling():
    from src.evaluation.result_validator import normalize_dimension_result

    dimension = _load_dimension("logical_coherence")
    result = DimensionResult(
        dimension="logical_coherence",
        score=64,
        band="good",
        summary="论证存在关键跳步。",
        core_judgment="核心结论无法由前文材料充分推出。",
        score_rationale="触发关键跳步规则，但模型仍给了高于上限的分数。",
        evidence_quotes=["这表明……应转而寻求一种正义的首要原则。"],
        strengths=["主线问题意识较明确"],
        weaknesses=["规范证成存在关键跳步"],
        limit_rule_triggered=[
            LimitRuleTriggered(
                rule_id="logical_coherence.broken_inference_chain",
                rule="存在关键跳步",
                score_ceiling=50,
                priority=1,
                evidence="从实然判断直接跳到规范结论。",
            )
        ],
        boundary_note="这是逻辑链条问题，不是框架问题。",
        review_flags=["counterargument_missing"],
        model_name="gpt-5.4",
    )

    normalized = normalize_dimension_result(result, dimension)

    assert normalized.score == 50


def test_normalize_dimension_result_rejects_unknown_rule_id():
    from src.evaluation.result_validator import normalize_dimension_result

    dimension = _load_dimension("logical_coherence")
    result = DimensionResult(
        dimension="logical_coherence",
        score=48,
        band="marginal",
        summary="模型返回了未定义规则。",
        core_judgment="结果包含框架中不存在的 rule_id。",
        score_rationale="未知规则不能被静默接受。",
        evidence_quotes=["核心结论无法由前文推出。"],
        strengths=[],
        weaknesses=["使用了未定义 rule_id"],
        limit_rule_triggered=[
            LimitRuleTriggered(
                rule_id="logical_coherence.inference_gap",
                rule="框架中不存在的规则",
                score_ceiling=90,
                priority=2,
                evidence="模型自造了 rule_id。",
            )
        ],
        boundary_note="这是协议校验问题。",
        review_flags=["evidence_thin"],
        model_name="z-ai/glm-5.1",
    )

    with pytest.raises(EvaluationError, match="未定义"):
        normalize_dimension_result(result, dimension)
