from __future__ import annotations

from typing import Any


def _legacy_weighted_total(
    dimension_scores: dict[str, float], dimension_weights: dict[str, float] | None
) -> float:
    if not dimension_weights:
        return 0.0
    return sum(dimension_scores.get(key, 0.0) * weight for key, weight in dimension_weights.items())


def _pick_ceiling(score: float, thresholds: list[dict[str, Any]]) -> float | None:
    for threshold in sorted(
        thresholds, key=lambda item: float(item.get("min_score", 0.0)), reverse=True
    ):
        if score >= float(threshold.get("min_score", 0.0)):
            ceiling = threshold.get("score_ceiling")
            return None if ceiling is None else float(ceiling)
    return None


def _pick_bonus(score: float, bands: list[dict[str, Any]], max_bonus: float) -> float:
    for band in sorted(bands, key=lambda item: float(item.get("min_score", 0.0)), reverse=True):
        if score >= float(band.get("min_score", 0.0)):
            return min(float(band.get("bonus", 0.0)), max_bonus)
    return 0.0


def _core_ceiling_bonus_total(
    dimension_scores: dict[str, float], protocol: dict[str, Any]
) -> float:
    core_dimensions = protocol.get("core_dimensions", [])
    if not core_dimensions:
        return 0.0

    core_weight_sum = sum(float(item.get("weight", 0.0)) for item in core_dimensions)
    if core_weight_sum <= 0:
        return 0.0

    core_weighted = sum(
        dimension_scores.get(str(item.get("key")), 0.0) * float(item.get("weight", 0.0))
        for item in core_dimensions
    )
    core_score = core_weighted / core_weight_sum

    bonus_dimension = protocol.get("bonus_dimension", {}) or {}
    bonus_key = str(bonus_dimension.get("key", ""))
    bonus = 0.0
    if bonus_key:
        prerequisites = bonus_dimension.get("prerequisites", {}) or {}
        logical_ok = dimension_scores.get("logical_coherence", 0.0) >= float(
            prerequisites.get("logical_coherence_min", 0.0)
        )
        consensus_ok = dimension_scores.get("conclusion_consensus", 0.0) >= float(
            prerequisites.get("conclusion_consensus_min", 0.0)
        )
        core_min = float(prerequisites.get("core_dimension_min", 0.0))
        core_ok = all(
            dimension_scores.get(str(item.get("key")), 0.0) >= core_min for item in core_dimensions
        )
        if logical_ok and consensus_ok and core_ok:
            bonus = _pick_bonus(
                score=dimension_scores.get(bonus_key, 0.0),
                bands=bonus_dimension.get("bands", []) or [],
                max_bonus=float(bonus_dimension.get("max_bonus", 0.0)),
            )

    subtotal = core_score + bonus

    ceiling_dimension = protocol.get("ceiling_dimension", {}) or {}
    ceiling_key = str(ceiling_dimension.get("key", ""))
    if not ceiling_key:
        return subtotal
    ceiling = _pick_ceiling(
        score=dimension_scores.get(ceiling_key, 0.0),
        thresholds=ceiling_dimension.get("thresholds", []) or [],
    )
    return subtotal if ceiling is None else min(subtotal, ceiling)


def calculate_weighted_total(
    dimension_scores: dict[str, float],
    scoring_protocol: dict[str, Any] | None = None,
    dimension_weights: dict[str, float] | None = None,
) -> float:
    if not scoring_protocol:
        return round(_legacy_weighted_total(dimension_scores, dimension_weights), 2)

    if scoring_protocol.get("mode") == "core_ceiling_bonus":
        return round(_core_ceiling_bonus_total(dimension_scores, scoring_protocol), 2)

    return round(_legacy_weighted_total(dimension_scores, dimension_weights), 2)
