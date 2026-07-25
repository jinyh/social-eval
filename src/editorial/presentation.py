"""编辑端中文展示与分歧摘要。

本模块只适配、聚合和翻译既有评价结果，不改变六维、五轴或 CCB 的计算。
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Any, Iterable

from src.editorial.decision import band_for_score
from src.editorial.policy import EditorialPolicy
from src.knowledge.registry import load_position_framework
from src.models.evaluation import DimensionScore
from src.models.reliability import ReliabilityResult


DIMENSION_LABELS = {
    "problem_originality": "研究创新性",
    "research_innovation": "研究创新性",
    "literature_insight": "现状洞察度",
    "problem_situation_insight": "现状洞察度",
    "analytical_framework": "理论建构力",
    "theoretical_construction": "理论建构力",
    "logical_coherence": "逻辑连贯性",
    "conclusion_consensus": "学术共识度",
    "scholarly_consensus": "学术共识度",
    "forward_extension": "前瞻延展性",
}

POSITION_AXES = tuple(load_position_framework()["axes"])

BAND_LABELS = {
    "excellent": "优",
    "good": "良",
    "marginal": "中",
    "unacceptable": "差",
}

_BAND_TEXT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(excellent|good|marginal|unacceptable)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中等",
    "low": "较低",
    "critical": "很低",
}

STRENGTH_LABELS = {
    "strong": "归属证据较强",
    "medium": "归属证据中等",
    "weak": "归属证据较弱",
    "absent": "尚无明确归属证据",
}


def localize_band_text(value: str) -> str:
    """把自然语言中的内部四档代码转换为中文展示值。"""

    return _BAND_TEXT_PATTERN.sub(
        lambda match: BAND_LABELS[match.group(1).lower()],
        value,
    )


def localize_synthesis_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """递归转换综合摘要中的档位代码，不触碰论文正文或证据字段。"""

    if not payload:
        return {}

    def normalize(value: Any) -> Any:
        if isinstance(value, str):
            return localize_band_text(value)
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    return {key: normalize(value) for key, value in payload.items()}


def dimension_label(
    key: str,
    configured_labels: dict[str, str] | None = None,
) -> str:
    """返回权威六维中文名称。"""

    if configured_labels and key in configured_labels:
        return configured_labels[key]
    return DIMENSION_LABELS.get(key, key)


def _confidence(std_score: float) -> str:
    if std_score <= 5:
        return "高"
    if std_score <= 8:
        return "中等"
    if std_score <= 12:
        return "较低"
    return "很低"


def build_six_dimension_summary(
    scores: Iterable[DimensionScore],
    reliability: Iterable[ReliabilityResult],
    policy: EditorialPolicy,
    provider_names: list[str],
    dimension_definitions: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """把最终轮四模型结果整理为匿名、可审计的编辑视图。"""

    configured_dimensions = list(dimension_definitions or [])
    configured_labels = dict(configured_dimensions)
    configured_order = {
        key: index for index, (key, _) in enumerate(configured_dimensions)
    }
    score_rows: dict[str, dict[str, DimensionScore]] = defaultdict(dict)
    for row in scores:
        score_rows[row.dimension_key][row.model_name] = row
    reliability_rows = {row.dimension_key: row for row in reliability}

    observed = {model_name for rows in score_rows.values() for model_name in rows}
    ordered_models = [name for name in provider_names if name in observed]
    ordered_models.extend(sorted(observed - set(ordered_models)))
    label_sequence = ("甲", "乙", "丙", "丁")
    anonymous_labels = {
        model_name: f"模型{label_sequence[index]}"
        for index, model_name in enumerate(ordered_models)
    }

    dimensions: list[dict[str, Any]] = []
    required_count = 0
    difference_count = 0
    for dimension_key, model_rows in score_rows.items():
        reliability_row = reliability_rows.get(dimension_key)
        values = [row.score for row in model_rows.values()]
        mean_score = (
            reliability_row.mean_score
            if reliability_row is not None
            else statistics.mean(values)
        )
        std_score = (
            reliability_row.std_score
            if reliability_row is not None
            else (statistics.stdev(values) if len(values) > 1 else 0.0)
        )
        model_results = []
        bands: set[str] = set()
        for model_name in ordered_models:
            row = model_rows.get(model_name)
            if row is None:
                continue
            payload = row.structured_payload or {}
            band = str(
                payload.get("band")
                or payload.get("revised_band")
                or band_for_score(row.score, policy)
            )
            bands.add(band)
            model_results.append(
                {
                    "model_label": anonymous_labels[model_name],
                    "score": round(row.score, 2),
                    "band": band,
                    "band_label": BAND_LABELS.get(band, band),
                    "evidence_quotes": row.evidence_quotes or [],
                    "analysis": row.analysis or "",
                }
            )

        if std_score > 8:
            difference_level = "expert_review"
            difference_label = "分歧较大，必须专家复核"
            required_count += 1
            difference_count += 1
        elif len(bands) > 1:
            difference_level = "band_difference"
            difference_label = "存在观点差异"
            difference_count += 1
        else:
            difference_level = "consensus"
            difference_label = "意见基本一致"
        aggregate_band = band_for_score(float(mean_score), policy)
        dimensions.append(
            {
                "dimension_key": dimension_key,
                "dimension_name": dimension_label(
                    dimension_key,
                    configured_labels,
                ),
                "mean_score": round(float(mean_score), 2),
                "std_score": round(float(std_score), 2),
                "confidence_label": _confidence(float(std_score)),
                "band": aggregate_band,
                "band_label": BAND_LABELS.get(aggregate_band, aggregate_band),
                "difference_level": difference_level,
                "difference_label": difference_label,
                "requires_expert_review": std_score > 8,
                "model_results": model_results,
            }
        )

    dimensions.sort(
        key=lambda item: configured_order.get(
            item["dimension_key"],
            (
                list(DIMENSION_LABELS).index(item["dimension_key"])
                if item["dimension_key"] in DIMENSION_LABELS
                else len(DIMENSION_LABELS)
            ),
        )
    )
    return {
        "model_participation": {
            "count": len(ordered_models),
            "labels": [anonymous_labels[name] for name in ordered_models],
        },
        "difference_count": difference_count,
        "expert_review_dimension_count": required_count,
        "dimensions": dimensions,
    }


def build_ccb_summary(aggregate: dict[str, Any] | None) -> dict[str, Any] | None:
    """把既有 CCB 聚合字段转换为中文展示结构。"""

    if not aggregate:
        return None
    ceiling = aggregate.get("conclusion_consensus_ceiling")
    return {
        "label": "核心—封顶—加分综合参考分",
        "base_score": float(aggregate.get("base_score", 0.0)),
        "bonus_score": float(aggregate.get("bonus_score", 0.0)),
        "ceiling_score": None if ceiling is None else float(ceiling),
        "ceiling_label": "未触发封顶" if ceiling is None else f"封顶至 {ceiling:g} 分",
        "final_score": float(aggregate.get("final_score", 0.0)),
        "notice": "仅供编辑参考，不作为录用或退稿阈值。",
    }


def build_position_summary(
    position_result: dict[str, Any] | None,
    *,
    precheck_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """整理五轴总分、折叠明细及与公共预检的矛盾提示。"""

    if not position_result:
        return None
    final = position_result.get("final")
    if not isinstance(final, dict):
        return None
    axes = final.get("axis_scores")
    axes = axes if isinstance(axes, dict) else {}
    details = []
    for axis in POSITION_AXES:
        key = str(axis["key"])
        payload = axes.get(key)
        payload = payload if isinstance(payload, dict) else {}
        details.append(
            {
                "axis_key": key,
                "axis_name": str(axis["name_zh"]),
                "focus_label": str(axis["focus_zh"]),
                "guiding_question": str(axis["question_zh"]),
                "score": int(payload.get("score", 0) or 0),
                "score_range": payload.get("score_range", [0, 0]),
                "evidence_quotes": payload.get("evidence_quotes", []),
                "has_model_difference": (
                    isinstance(payload.get("score_range"), list)
                    and len(payload["score_range"]) == 2
                    and payload["score_range"][0] != payload["score_range"][1]
                ),
            }
        )

    total = int(final.get("total_score", 0) or 0)
    precheck_conclusion = (
        str((precheck_result or {}).get("conclusion", "")) if precheck_result else ""
    )
    boundary = precheck_conclusion in {"boundary_review", "obviously_ineligible"}
    conflict = total >= 8 and boundary
    return {
        "total_score": total,
        "strength_label": STRENGTH_LABELS.get(str(final.get("strength", "")), "待确认"),
        "confidence_label": CONFIDENCE_LABELS.get(
            str(final.get("confidence", "")), str(final.get("confidence", "待确认"))
        ),
        "agreement_label": {
            "high": "两模型意见一致",
            "medium": "两模型存在局部差异",
            "low": "两模型分歧较大",
            "none": "缺少有效模型结果",
        }.get(str(final.get("agreement_level", "")), "待确认"),
        "review_required": bool(final.get("review_required", False)),
        "conflict_with_precheck": conflict,
        "conflict_message": (
            "五轴高分与公共预检的边界判断不一致，需核对中国法和知识体系归属证据。"
            if conflict
            else None
        ),
        "axes": details,
        "notice": "五轴评价知识体系位置归属，不评价论文质量，也不参与录退决定。",
    }
