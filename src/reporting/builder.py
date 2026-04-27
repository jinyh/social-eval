from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from src.evaluation.defaults import DEFAULT_FRAMEWORK_PATH, DEFAULT_PROVIDER_NAMES
from src.knowledge.loader import load_framework
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.reporting.charts import generate_radar_chart_base64
from src.reporting.scoring import calculate_weighted_total
from src.reporting.summary_extractor import extract_dimension_summary


def _decode_provider_names(raw_provider_names: str | None) -> list[str]:
    if not raw_provider_names:
        return list(DEFAULT_PROVIDER_NAMES)
    try:
        provider_names = json.loads(raw_provider_names)
    except json.JSONDecodeError:
        return list(DEFAULT_PROVIDER_NAMES)
    if not isinstance(provider_names, list):
        return list(DEFAULT_PROVIDER_NAMES)
    return [str(name) for name in provider_names]


def _dimension_result_payload(score: DimensionScore) -> dict[str, Any]:
    if not score.analysis:
        return {}
    try:
        payload = json.loads(score.analysis)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _score_analysis_text(score: DimensionScore, payload: dict[str, Any]) -> str | None:
    if text := _payload_text(payload, "score_rationale"):
        return text
    if text := _payload_text(payload, "analysis"):
        return text
    return score.analysis


def _first_text(values: list[str]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _conclusion_for_score(score: float) -> str:
    if score < 50:
        return "不建议进入人工深审"
    if score < 70:
        return "边界稿，建议专家复核"
    return "可进入专家深审"


def build_internal_report(db: Session, task: EvaluationTask, paper: Paper) -> dict:
    framework = load_framework(task.framework_path or DEFAULT_FRAMEWORK_PATH)
    score_rows = db.query(DimensionScore).filter(DimensionScore.task_id == task.id).all()
    reliability_rows = {
        row.dimension_key: row
        for row in db.query(ReliabilityResult).filter(ReliabilityResult.task_id == task.id).all()
    }
    review_rows = db.query(ExpertReview).filter(ExpertReview.task_id == task.id).all()
    review_ids = [review.id for review in review_rows]
    comments_by_review: dict[str, list[ReviewComment]] = defaultdict(list)
    if review_ids:
        comment_rows = db.query(ReviewComment).filter(ReviewComment.review_id.in_(review_ids)).all()
        for comment in comment_rows:
            comments_by_review[comment.review_id].append(comment)

    scores_by_dimension: dict[str, list[DimensionScore]] = defaultdict(list)
    for score in score_rows:
        scores_by_dimension[score.dimension_key].append(score)

    dimensions = []
    mean_scores_by_dimension: dict[str, float] = {}
    dimension_weights: dict[str, float] = {}
    radar_labels: list[str] = []
    radar_values: list[float] = []

    for dimension in framework.dimensions:
        reliability = reliability_rows.get(dimension.key)
        per_dimension_scores = scores_by_dimension.get(dimension.key, [])
        result_payloads = [_dimension_result_payload(score) for score in per_dimension_scores]
        summaries = [
            text
            for payload in result_payloads
            if (text := _payload_text(payload, "summary"))
        ]
        rationale_texts = [
            text
            for payload in result_payloads
            if (text := _payload_text(payload, "score_rationale") or _payload_text(payload, "analysis"))
        ]
        analyses = [score.analysis for score in per_dimension_scores if score.analysis]
        summary = _first_text(summaries) or extract_dimension_summary(
            "。".join(rationale_texts or analyses)
        )
        mean_score = reliability.mean_score if reliability else 0.0
        mean_scores_by_dimension[dimension.key] = mean_score
        dimension_weights[dimension.key] = dimension.weight
        radar_labels.append(dimension.name_en)
        radar_values.append(mean_score)
        dimensions.append(
            {
                "key": dimension.key,
                "name_zh": dimension.name_zh,
                "name_en": dimension.name_en,
                "weight": dimension.weight,
                "summary": summary,
                "ai": {
                    "mean_score": mean_score,
                    "std_score": reliability.std_score if reliability else 0.0,
                    "is_high_confidence": reliability.is_high_confidence if reliability else True,
                    "model_scores": reliability.model_scores if reliability else {},
                    "evidence_quotes": [
                        score.evidence_quotes
                        for score in per_dimension_scores
                        if score.evidence_quotes
                    ],
                    "analysis": [
                        score.analysis for score in per_dimension_scores if score.analysis
                    ],
                    "model_details": [
                        {
                            "model_name": score.model_name,
                            "score": score.score,
                            "summary": payload.get("summary"),
                            "core_judgment": payload.get("core_judgment"),
                            "score_rationale": _score_analysis_text(score, payload),
                            "strengths": payload.get("strengths", []),
                            "weaknesses": payload.get("weaknesses", []),
                            "limit_rule_triggered": payload.get("limit_rule_triggered", []),
                            "boundary_note": payload.get("boundary_note"),
                            "review_flags": payload.get("review_flags", []),
                            "evidence_quotes": score.evidence_quotes or [],
                        }
                        for score, payload in zip(per_dimension_scores, result_payloads)
                    ],
                },
            }
        )

    expert_reviews = []
    expert_scores_by_dimension: dict[str, list[float]] = defaultdict(list)
    for review in review_rows:
        review_comments = comments_by_review.get(review.id, [])
        if review.status == "submitted":
            for comment in review_comments:
                expert_scores_by_dimension[comment.dimension_key].append(comment.expert_score)
        expert_reviews.append(
            {
                "review_id": review.id,
                "expert_id": review.expert_id,
                "status": review.status,
                "version": review.version,
                "completed_at": review.completed_at.isoformat() if review.completed_at else None,
                "comments": [
                    {
                        "dimension_key": comment.dimension_key,
                        "ai_score": comment.ai_score,
                        "expert_score": comment.expert_score,
                        "reason": comment.reason,
                    }
                    for comment in review_comments
                ],
            }
        )

    ai_weighted_total = calculate_weighted_total(
        dimension_scores=mean_scores_by_dimension,
        scoring_protocol=framework.raw_config.get("scoring_protocol"),
        dimension_weights=dimension_weights,
    )
    final_scores_by_dimension = dict(mean_scores_by_dimension)
    for dimension_key, scores in expert_scores_by_dimension.items():
        final_scores_by_dimension[dimension_key] = sum(scores) / len(scores)

    weighted_total = calculate_weighted_total(
        dimension_scores=final_scores_by_dimension,
        scoring_protocol=framework.raw_config.get("scoring_protocol"),
        dimension_weights=dimension_weights,
    )
    expert_adjusted_total = weighted_total if expert_scores_by_dimension else None
    expert_review_required = any(
        not (dimension["ai"]["is_high_confidence"]) for dimension in dimensions
    ) or task.manual_review_requested

    return {
        "report_type": "internal",
        "paper_id": paper.id,
        "task_id": task.id,
        "framework": {
            "name": framework.name,
            "version": framework.version,
            "path": task.framework_path or DEFAULT_FRAMEWORK_PATH,
        },
        "models": _decode_provider_names(task.provider_names),
        "paper_title": paper.title or paper.original_filename,
        "title": paper.title or paper.original_filename,
        "precheck_status": paper.precheck_status,
        "precheck_result": paper.precheck_result,
        "ai_weighted_total": ai_weighted_total,
        "expert_adjusted_total": expert_adjusted_total,
        "weighted_total": weighted_total,
        "conclusion": _conclusion_for_score(weighted_total),
        "expert_review_required": expert_review_required,
        "radar_chart": {
            "labels": radar_labels,
            "values": radar_values,
            "image_base64": generate_radar_chart_base64(radar_labels, radar_values),
        },
        "dimensions": dimensions,
        "expert_reviews": expert_reviews,
    }
