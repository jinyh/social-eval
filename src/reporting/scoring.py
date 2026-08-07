from __future__ import annotations

from typing import Any


def _legacy_weighted_total(
    dimension_scores: dict[str, float], dimension_weights: dict[str, float] | None
) -> float:
    if not dimension_weights:
        return 0.0
    return sum(
        dimension_scores.get(key, 0.0) * weight
        for key, weight in dimension_weights.items()
    )


def pick_ceiling(score: float, thresholds: list[dict[str, Any]]) -> float | None:
    """根据学术共识度分数查表确定总分上限（None 表示不上限）。"""
    for threshold in sorted(
        thresholds, key=lambda item: float(item.get("min_score", 0.0)), reverse=True
    ):
        if score >= float(threshold.get("min_score", 0.0)):
            ceiling = threshold.get("score_ceiling")
            return None if ceiling is None else float(ceiling)
    return None


def pick_bonus(score: float, bands: list[dict[str, Any]], max_bonus: float) -> float:
    """根据前瞻延展性分数查表确定加分。"""
    for band in sorted(
        bands, key=lambda item: float(item.get("min_score", 0.0)), reverse=True
    ):
        if score >= float(band.get("min_score", 0.0)):
            return min(float(band.get("bonus", 0.0)), max_bonus)
    return 0.0


# 兼容别名：保留私有名供既有调用
_pick_ceiling = pick_ceiling
_pick_bonus = pick_bonus


def compute_base_score(
    dimension_scores: dict[str, float], protocol: dict[str, Any]
) -> float:
    """按 scoring_protocol.core_dimensions 计算基础分（核心四维加权平均）。"""
    core_dimensions = protocol.get("core_dimensions", []) or []
    if not core_dimensions:
        return 0.0

    core_weight_sum = sum(float(item.get("weight", 0.0)) for item in core_dimensions)
    if core_weight_sum <= 0:
        return 0.0

    core_weighted = sum(
        dimension_scores.get(str(item.get("key")), 0.0) * float(item.get("weight", 0.0))
        for item in core_dimensions
    )
    return core_weighted / core_weight_sum


def compute_bonus(
    dimension_scores: dict[str, float], protocol: dict[str, Any]
) -> float:
    """按 scoring_protocol.bonus_dimension 计算前瞻延展加分。

    需满足 prerequisites：逻辑连贯性 >= 60、学术共识度 >= 60、核心四维均 >= 50。
    """
    bonus_dimension = protocol.get("bonus_dimension", {}) or {}
    bonus_key = str(bonus_dimension.get("key", ""))
    if not bonus_key:
        return 0.0

    prerequisites = bonus_dimension.get("prerequisites", {}) or {}
    core_min = float(prerequisites.get("core_dimension_min", 0.0))
    # 维度级前提从字段名（如 logical_coherence_min）派生 key，不在代码中硬编码
    # 具体维度名；core_dimension_min 是通用阈值，不对应单个维度。
    dimension_prereqs = {
        name.removesuffix("_min"): float(value)
        for name, value in prerequisites.items()
        if name.endswith("_min") and name != "core_dimension_min"
    }
    dimension_prereqs_ok = all(
        dimension_scores.get(dim_key, 0.0) >= threshold
        for dim_key, threshold in dimension_prereqs.items()
    )
    core_dimensions = protocol.get("core_dimensions", []) or []
    core_ok = all(
        dimension_scores.get(str(item.get("key")), 0.0) >= core_min
        for item in core_dimensions
    )
    if not (dimension_prereqs_ok and core_ok):
        return 0.0

    return pick_bonus(
        score=dimension_scores.get(bonus_key, 0.0),
        bands=bonus_dimension.get("bands", []) or [],
        max_bonus=float(bonus_dimension.get("max_bonus", 0.0)),
    )


def compute_ceiling(
    dimension_scores: dict[str, float], protocol: dict[str, Any]
) -> float | None:
    """按 scoring_protocol.ceiling_dimension 计算学术共识度上限。"""
    ceiling_dimension = protocol.get("ceiling_dimension", {}) or {}
    ceiling_key = str(ceiling_dimension.get("key", ""))
    if not ceiling_key:
        return None
    return pick_ceiling(
        score=dimension_scores.get(ceiling_key, 0.0),
        thresholds=ceiling_dimension.get("thresholds", []) or [],
    )


def _core_ceiling_bonus_total(
    dimension_scores: dict[str, float], protocol: dict[str, Any]
) -> float:
    base = compute_base_score(dimension_scores, protocol)
    bonus = compute_bonus(dimension_scores, protocol)
    subtotal = base + bonus
    ceiling = compute_ceiling(dimension_scores, protocol)
    total = subtotal if ceiling is None else min(subtotal, ceiling)
    return min(total, float(protocol.get("total_max", 100.0)))


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
