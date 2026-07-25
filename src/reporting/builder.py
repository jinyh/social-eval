from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy.orm import Session

from src.knowledge.loader import load_framework
from src.editorial.presentation import dimension_label
from src.knowledge.registry import load_model_set, resolve_framework_path
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.reporting.charts import generate_radar_chart_base64
from src.reporting.scoring import calculate_weighted_total
from src.reporting.summary_extractor import extract_dimension_summary


def build_internal_report(db: Session, task: EvaluationTask, paper: Paper) -> dict:
    framework = load_framework(task.framework_path or resolve_framework_path())
    score_rows = (
        db.query(DimensionScore)
        .filter(
            DimensionScore.task_id == task.id,
            DimensionScore.round_number == task.final_round,
        )
        .all()
    )
    reliability_rows = {
        row.dimension_key: row
        for row in db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .all()
    }
    reliability_history: dict[str, dict[int, ReliabilityResult]] = defaultdict(dict)
    for row in (
        db.query(ReliabilityResult).filter(ReliabilityResult.task_id == task.id).all()
    ):
        reliability_history[row.dimension_key][row.round_number] = row
    review_rows = db.query(ExpertReview).filter(ExpertReview.task_id == task.id).all()
    review_ids = [review.id for review in review_rows]
    comments_by_review: dict[str, list[ReviewComment]] = defaultdict(list)
    if review_ids:
        comment_rows = (
            db.query(ReviewComment)
            .filter(ReviewComment.review_id.in_(review_ids))
            .all()
        )
        for comment in comment_rows:
            comments_by_review[comment.review_id].append(comment)

    scores_by_dimension: dict[str, list[DimensionScore]] = defaultdict(list)
    for score in score_rows:
        scores_by_dimension[score.dimension_key].append(score)
    ordered_models = _ordered_model_names(task, score_rows)
    anonymous_model_labels = {
        model_name: f"模型{label}"
        for model_name, label in zip(
            ordered_models,
            ("甲", "乙", "丙", "丁"),
            strict=False,
        )
    }

    dimensions = []
    mean_scores_by_dimension: dict[str, float] = {}
    dimension_weights: dict[str, float] = {}
    radar_labels: list[str] = []
    radar_values: list[float] = []

    for dimension in framework.dimensions:
        reliability = reliability_rows.get(dimension.key)
        per_dimension_scores = scores_by_dimension.get(dimension.key, [])
        mean_score = reliability.mean_score if reliability else 0.0
        mean_scores_by_dimension[dimension.key] = mean_score
        dimension_weights[dimension.key] = dimension.weight
        display_name = dimension_label(dimension.key)
        radar_labels.append(display_name)
        radar_values.append(mean_score)

        # 从第一个有 analysis 的评分中提取总结
        analysis_texts = [
            score.analysis for score in per_dimension_scores if score.analysis
        ]
        summary = extract_dimension_summary(analysis_texts[0]) if analysis_texts else ""
        scores_by_model = {score.model_name: score for score in per_dimension_scores}
        model_results = []
        for model_name in ordered_models:
            score = scores_by_model.get(model_name)
            if score is None:
                continue
            model_results.append(
                {
                    "model_label": anonymous_model_labels[model_name],
                    "score": round(score.score, 2),
                    "evidence_quotes": score.evidence_quotes or [],
                    "analysis": score.analysis or "",
                }
            )

        dimensions.append(
            {
                "key": dimension.key,
                "name_zh": display_name,
                "name_en": dimension.name_en,
                "weight": dimension.weight,
                "ai": {
                    "mean_score": round(mean_score, 2),
                    "std_score": round(reliability.std_score, 2)
                    if reliability
                    else 0.0,
                    "is_high_confidence": reliability.is_high_confidence
                    if reliability
                    else True,
                    "model_scores": reliability.model_scores if reliability else {},
                    "model_results": model_results,
                    "evidence_quotes": [
                        score.evidence_quotes
                        for score in per_dimension_scores
                        if score.evidence_quotes
                    ],
                    "analysis": analysis_texts,
                    "summary": summary,
                    "rounds": {
                        str(round_number): {
                            "mean_score": round(round_row.mean_score, 2),
                            "std_score": round(round_row.std_score, 2),
                            "model_scores": round_row.model_scores or {},
                        }
                        for round_number, round_row in sorted(
                            reliability_history.get(dimension.key, {}).items()
                        )
                    },
                },
            }
        )

    expert_reviews = []
    for review in review_rows:
        expert_reviews.append(
            {
                "review_id": review.id,
                "expert_id": review.expert_id,
                "status": review.status,
                "version": review.version,
                "completed_at": review.completed_at.isoformat()
                if review.completed_at
                else None,
                "comments": [
                    {
                        "dimension_key": comment.dimension_key,
                        "ai_score": comment.ai_score,
                        "expert_score": comment.expert_score,
                        "reason": comment.reason,
                        "statement_decisions": comment.statement_decisions,
                        "comparison_reason": comment.comparison_reason,
                    }
                    for comment in comments_by_review.get(review.id, [])
                ],
            }
        )

    return {
        "report_type": "internal",
        "paper_id": paper.id,
        "task_id": task.id,
        "final_round": task.final_round,
        "paper_title": paper.title or paper.original_filename,
        "precheck_status": paper.precheck_status,
        "precheck_result": paper.precheck_result,
        # v2.45 D 路径新增字段：旧 Paper 未写入时为 None（向后兼容）
        "signal_check_result": paper.signal_check_result,
        "aggregate_result": paper.aggregate_result,
        "weighted_total": calculate_weighted_total(
            dimension_scores=mean_scores_by_dimension,
            scoring_protocol=framework.raw_config.get("scoring_protocol"),
            dimension_weights=dimension_weights,
        ),
        "radar_chart": {
            "labels": radar_labels,
            "values": [round(v, 2) for v in radar_values],
            "image_base64": generate_radar_chart_base64(radar_labels, radar_values),
        },
        "dimensions": dimensions,
        "expert_reviews": expert_reviews,
    }


def _ordered_model_names(
    task: EvaluationTask,
    score_rows: list[DimensionScore],
) -> list[str]:
    """按版本化模型集排序；历史任务则使用任务快照和稳定回退。"""

    observed = {row.model_name for row in score_rows}
    configured: list[str] = []
    try:
        configured = load_model_set(task.model_set_version)["provider_names"]
    except (KeyError, ValueError):
        if task.provider_names:
            try:
                payload = json.loads(task.provider_names)
                if isinstance(payload, list):
                    configured = [str(item) for item in payload]
            except json.JSONDecodeError:
                configured = []
    ordered = [name for name in configured if name in observed]
    ordered.extend(sorted(observed - set(ordered)))
    return ordered[:4]
