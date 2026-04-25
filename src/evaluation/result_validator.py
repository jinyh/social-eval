from __future__ import annotations

from src.core.exceptions import EvaluationError
from src.evaluation.schemas import DimensionResult
from src.knowledge.schemas import Dimension


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
