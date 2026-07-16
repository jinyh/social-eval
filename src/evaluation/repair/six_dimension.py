"""六维与 E2 混合格式的缺口扫描、合并和统计重算。"""

from __future__ import annotations

import copy
import statistics
from collections.abc import Mapping
from typing import Any

from src.evaluation.repair.models import Gap, RepairTarget, SIX_DIMENSION_MODELS
from src.reporting.scoring import calculate_weighted_total


def is_valid_score(value: Any) -> bool:
    """判断值是否为 0 到 100 的数值评分。"""

    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 100


def score_field(dimension: Mapping[str, Any], round_number: int) -> str:
    """返回某种历史格式在指定轮次使用的评分字段。"""

    if round_number == 2:
        return "round2_scores"
    if "model_scores" in dimension and "round1_scores" not in dimension:
        return "model_scores"
    return "round1_scores"


def round_scores(dimension: Mapping[str, Any], round_number: int) -> dict[str, Any]:
    """以统一接口读取一个维度的指定轮评分。"""

    scores = dimension.get(score_field(dimension, round_number), {})
    return dict(scores) if isinstance(scores, Mapping) else {}


def scan_six_dimension_gaps(
    target: RepairTarget,
    paper_id: int,
    result: Mapping[str, Any],
) -> list[Gap]:
    """扫描标准六维、自包含 E2 或 legacy E2 的模型评分缺口。"""

    if target.family not in {"six_dimension", "e2"}:
        raise ValueError(f"目标不是六维/E2：{target.key}")
    rounds = (target.round_number,) if target.family == "e2" else (1, 2)
    dimensions = result.get("dimensions", {})
    if not isinstance(dimensions, Mapping):
        dimensions = {}

    gaps: list[Gap] = []
    dimension_keys = target.expected_dimensions or tuple(str(key) for key in dimensions)
    for dimension_key in dimension_keys:
        dimension = dimensions.get(dimension_key)
        missing_dimension = not isinstance(dimension, Mapping)
        if missing_dimension:
            dimension = {}
        for round_number in rounds:
            if round_number is None:
                continue
            scores = round_scores(dimension, round_number)
            for model in SIX_DIMENSION_MODELS:
                value = scores.get(model)
                if is_valid_score(value):
                    continue
                if missing_dimension:
                    reason = "missing_dimension"
                else:
                    reason = "missing_score" if model not in scores else "invalid_score"
                gaps.append(
                    Gap(
                        target_key=target.key,
                        paper_id=paper_id,
                        dimension=str(dimension_key),
                        round_number=round_number,
                        model=model,
                        reason=reason,
                    )
                )
    return gaps


def _response_score(response: Mapping[str, Any], round_number: int) -> int | float:
    key = "score" if round_number == 1 else "revised_score"
    value = response.get(key)
    if not is_valid_score(value):
        raise ValueError(f"模型响应缺少有效 {key}：{value!r}")
    return value


def merge_model_response(
    result: Mapping[str, Any],
    gap: Gap,
    response: Mapping[str, Any],
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """把一个槽位的模型响应合入副本，绝不覆盖已有有效评分。"""

    merged = copy.deepcopy(dict(result))
    dimensions = merged.setdefault("dimensions", {})
    if gap.dimension not in dimensions:
        raise KeyError(f"维度不存在：{gap.dimension}")
    dimension = dimensions[gap.dimension]
    field = score_field(dimension, gap.round_number)
    scores = dimension.setdefault(field, {})
    if is_valid_score(scores.get(gap.model)):
        raise ValueError(f"拒绝覆盖已有有效评分：{gap.slot_key}")

    value = _response_score(response, gap.round_number)
    scores[gap.model] = value
    if gap.round_number == 1:
        dimension.setdefault("raw_outputs", {})[gap.model] = copy.deepcopy(dict(response))
        errors = dimension.get("errors")
        if isinstance(errors, dict):
            errors.pop(gap.model, None)
    else:
        dimension.setdefault("round2_raw_outputs", {})[gap.model] = copy.deepcopy(
            dict(response)
        )
        original = round_scores(dimension, 1).get(gap.model)
        dimension.setdefault("changes", {})[gap.model] = {
            "original": original,
            "revised": value,
            "changed": response.get("score_changed", original != value),
            "direction": response.get("change_direction", "unchanged"),
            "magnitude": response.get(
                "change_magnitude",
                abs(value - original) if is_valid_score(original) else None,
            ),
            "confidence": response.get("confidence", "medium"),
        }
    dimension.setdefault("repair_elapsed_times", {})[
        f"r{gap.round_number}:{gap.model}"
    ] = round(elapsed_seconds, 3)
    merged.setdefault("repair_provenance", []).append(
        {
            "slot_key": gap.slot_key,
            "reason": gap.reason,
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
    )
    return merged


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0


def _std(values: list[float]) -> float:
    return round(statistics.stdev(values), 1) if len(values) > 1 else 0.0


def _confidence(std: float) -> str:
    if std <= 5:
        return "high"
    if std <= 8:
        return "medium"
    if std <= 12:
        return "low"
    return "critical"


def _numeric_scores(dimension: Mapping[str, Any], round_number: int) -> dict[str, float]:
    return {
        model: float(value)
        for model, value in round_scores(dimension, round_number).items()
        if is_valid_score(value)
    }


def _recompute_dimension(dimension: dict[str, Any]) -> None:
    r1 = _numeric_scores(dimension, 1)
    r2 = _numeric_scores(dimension, 2)
    r1_values = list(r1.values())
    r2_values = list(r2.values())

    if "model_scores" in dimension and "round1_scores" not in dimension:
        dimension["mean"] = _mean(r1_values)
        dimension["std"] = _std(r1_values)
        dimension["confidence"] = _confidence(dimension["std"])
        if r1_values:
            strictest = min(r1_values)
            dimension["strictest"] = strictest
            dimension["strictest_model"] = next(
                model for model, score in r1.items() if score == strictest
            )
        return

    dimension["round1_mean"] = _mean(r1_values)
    dimension["round1_std"] = _std(r1_values)
    if r2_values:
        dimension["round2_mean"] = _mean(r2_values)
        dimension["round2_std"] = _std(r2_values)
        dimension["convergence_improvement"] = round(
            dimension["round1_std"] - dimension["round2_std"], 1
        )


def recompute_result_statistics(
    result: Mapping[str, Any],
    *,
    scoring_protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """按结果原有格式重算维度与总体统计。"""

    recomputed = copy.deepcopy(dict(result))
    dimensions = recomputed.get("dimensions", {})
    if not isinstance(dimensions, dict):
        return recomputed
    for dimension in dimensions.values():
        if isinstance(dimension, dict):
            _recompute_dimension(dimension)

    legacy = any(
        isinstance(dimension, Mapping)
        and "model_scores" in dimension
        and "round1_scores" not in dimension
        for dimension in dimensions.values()
    )
    overall = recomputed.setdefault("overall", {})
    if legacy:
        stds = [
            float(dimension.get("std", 0))
            for dimension in dimensions.values()
            if isinstance(dimension, Mapping)
        ]
        overall["avg_std"] = _mean(stds)
        overall["max_std"] = round(max(stds), 1) if stds else 0.0
        overall["high_confidence_pct"] = round(
            100
            * sum(
                1
                for dimension in dimensions.values()
                if isinstance(dimension, Mapping)
                and dimension.get("confidence") == "high"
            )
            / len(dimensions),
            1,
        ) if dimensions else 0.0
        overall["dimension_count"] = len(dimensions)
        if scoring_protocol is not None:
            means = {
                key: float(dimension.get("mean", 0))
                for key, dimension in dimensions.items()
                if isinstance(dimension, Mapping)
            }
            strictest = {
                key: float(dimension.get("strictest", 0))
                for key, dimension in dimensions.items()
                if isinstance(dimension, Mapping)
            }
            overall.setdefault("aggregation_mean", {})["final_score"] = (
                calculate_weighted_total(means, dict(scoring_protocol))
            )
            overall.setdefault("aggregation_strictest", {})["final_score"] = (
                calculate_weighted_total(strictest, dict(scoring_protocol))
            )
        return recomputed

    r1_stds: list[float] = []
    r2_stds: list[float] = []
    all_r1: list[float] = []
    all_r2: list[float] = []
    for dimension in dimensions.values():
        if not isinstance(dimension, Mapping):
            continue
        r1_stds.append(float(dimension.get("round1_std", 0)))
        all_r1.extend(_numeric_scores(dimension, 1).values())
        r2_scores = _numeric_scores(dimension, 2)
        if r2_scores:
            r2_stds.append(float(dimension.get("round2_std", 0)))
            all_r2.extend(r2_scores.values())

    overall["round1_avg_std"] = round(statistics.mean(r1_stds), 2) if r1_stds else 0
    overall["round2_avg_std"] = round(statistics.mean(r2_stds), 2) if r2_stds else 0
    overall["std_improvement"] = round(
        overall["round1_avg_std"] - overall["round2_avg_std"], 2
    )
    if "round1_max_std" in overall or "round2_max_std" in overall:
        overall["round1_max_std"] = max(r1_stds, default=0)
        overall["round2_max_std"] = max(r2_stds, default=0)
    overall["dimensions_converged"] = sum(std <= 8 for std in r2_stds)
    total_key = "dimensions_total" if "dimensions_total" in overall else "total_dimensions"
    overall[total_key] = len(r2_stds)
    overall["round1_final_score_mean"] = round(statistics.mean(all_r1), 2) if all_r1 else 0
    overall["round2_final_score_mean"] = round(statistics.mean(all_r2), 2) if all_r2 else 0
    return recomputed
