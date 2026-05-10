from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, Field

from src.core.exceptions import EvaluationError
from src.evaluation.precheck import PrecheckResult
from src.evaluation.schemas import DimensionResult, SignalCheckResult
from src.knowledge.schemas import Dimension, Framework
from src.reliability.schemas import ReliabilityReport
from src.reporting.scoring import (
    compute_base_score,
    compute_bonus,
    compute_ceiling,
)


def _rule_ceiling_map(dimension: Dimension) -> dict[str, int]:
    model_extra = getattr(dimension, "model_extra", None) or {}
    rules = model_extra.get("ceiling_rules", [])
    rule_map: dict[str, int] = {}

    for rule in rules:
        rule_id = rule.get("rule_id")
        score_ceiling = rule.get("score_ceiling")
        if isinstance(rule_id, str) and isinstance(score_ceiling, int | float):
            rule_map[rule_id] = int(score_ceiling)

    return rule_map


def normalize_dimension_result(
    result: DimensionResult,
    dimension: Dimension,
) -> DimensionResult:
    if not result.limit_rule_triggered:
        return result

    ceiling_map = _rule_ceiling_map(dimension)
    normalized_rules = []
    active_ceilings: list[int] = []

    for triggered in result.limit_rule_triggered:
        configured_ceiling = ceiling_map.get(triggered.rule_id)
        if configured_ceiling is None:
            raise EvaluationError(
                f"维度 {dimension.key} 返回了未定义的 rule_id: {triggered.rule_id}"
            )

        active_ceilings.append(configured_ceiling)
        normalized_rules.append(
            triggered.model_copy(update={"score_ceiling": configured_ceiling})
        )

    normalized_score = min(result.score, min(active_ceilings))
    return result.model_copy(
        update={
            "score": normalized_score,
            "limit_rule_triggered": normalized_rules,
        }
    )


# =====================================================================
# v2.45 D 路径聚合契约输出（对应 v0.14 §7.1 aggregate_output_contract）
# =====================================================================


class MultiModelStats(BaseModel):
    mean: float
    std: float
    confidence_label: str  # high | medium | low | critical


class AggregateResult(BaseModel):
    """聚合层输出（v0.14 §7.1 / v2.44+ aggregate_output_contract）。

    由 orchestrator 在六维评分与信号校验完成后调用，结果持久化到
    papers.aggregate_result。
    """

    precheck_conclusion: str  # enter_six_dimension_review | boundary_review | obviously_ineligible
    base_score: float
    bonus_score: float
    conclusion_consensus_ceiling: float | None
    final_score: float
    multi_model_stats: MultiModelStats | None = None
    review_status: str  # none | recommended | required
    review_level: str  # precheck_level | evaluation_level | none
    triage_recommendation: str
    triggered_rules: list[str] = Field(default_factory=list)


# 预检结论到分流建议的映射（对应 v0.14 §2.2）
_PRECHECK_TO_TRIAGE = {
    "enter_six_dimension_review": "enter_six_dim",
    "boundary_review": "boundary_with_review",
    "obviously_ineligible": "obviously_ineligible_manual_confirm",
}


def _compute_multi_model_stats(
    reliability_reports: list[ReliabilityReport], framework: Framework
) -> MultiModelStats | None:
    """从 reliability_reports 聚合总体置信度。

    取所有 std 的平均值作为整体 std；按 framework.std_threshold 归类 label。
    """

    if not reliability_reports:
        return None

    means = [r.mean for r in reliability_reports]
    stds = [r.std for r in reliability_reports]
    overall_mean = statistics.mean(means)
    overall_std = statistics.mean(stds)

    threshold = framework.std_threshold
    if overall_std <= threshold:
        label = "high"
    elif overall_std <= threshold + 3:
        label = "medium"
    elif overall_std <= threshold + 7:
        label = "low"
    else:
        label = "critical"

    return MultiModelStats(mean=overall_mean, std=overall_std, confidence_label=label)


def _determine_review(
    precheck_conclusion: str, contradiction_rules: list[str]
) -> tuple[str, str]:
    """合并预检层复核与评价层复核，返回 (review_status, review_level)。"""

    if precheck_conclusion == "obviously_ineligible":
        return "required", "precheck_level"
    if precheck_conclusion == "boundary_review":
        return "required", "precheck_level"
    if contradiction_rules:
        return "required", "evaluation_level"
    return "none", "none"


def aggregate_result(
    dimension_scores: dict[str, float],
    precheck_result: PrecheckResult,
    signal_result: SignalCheckResult | None,
    reliability_reports: list[ReliabilityReport],
    framework: Framework,
    contradiction_rules: list[str] | None = None,
) -> AggregateResult:
    """按 aggregate_output_contract 聚合所有评估产物。

    - 复用 src/reporting/scoring.py 的 compute_base_score / compute_bonus / compute_ceiling
    - precheck_conclusion 透传自 precheck 适配层
    - review_status / review_level 合并预检与信号校验两个来源
    """

    protocol = framework.raw_config.get("scoring_protocol") or {}
    base = round(compute_base_score(dimension_scores, protocol), 2)
    bonus = round(compute_bonus(dimension_scores, protocol), 2)
    ceiling_val = compute_ceiling(dimension_scores, protocol)

    subtotal = base + bonus
    final = subtotal if ceiling_val is None else min(subtotal, ceiling_val)
    final = round(final, 2)

    # precheck_conclusion 优先取适配层填充值；若旧框架未填充，按默认值
    conclusion = precheck_result.conclusion or "enter_six_dimension_review"

    rules = list(contradiction_rules or [])
    if signal_result and signal_result.triggers_review and signal_result.review_reason:
        if signal_result.review_reason not in rules:
            rules.append(signal_result.review_reason)

    review_status, review_level = _determine_review(conclusion, rules)
    triage = _PRECHECK_TO_TRIAGE.get(conclusion, "enter_six_dim")

    return AggregateResult(
        precheck_conclusion=conclusion,
        base_score=base,
        bonus_score=bonus,
        conclusion_consensus_ceiling=(
            None if ceiling_val is None else float(ceiling_val)
        ),
        final_score=final,
        multi_model_stats=_compute_multi_model_stats(reliability_reports, framework),
        review_status=review_status,
        review_level=review_level,
        triage_recommendation=triage,
        triggered_rules=rules,
    )


def aggregate_result_to_dict(result: AggregateResult) -> dict[str, Any]:
    """序列化为 papers.aggregate_result 落库的 JSON 结构。"""
    return result.model_dump()
