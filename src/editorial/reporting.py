from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialOpinion,
    EditorialSubmission,
    PositionAssessment,
)
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.editorial.policy import load_editorial_policy
from src.editorial.presentation import (
    build_ccb_summary,
    build_position_summary,
    build_six_dimension_summary,
)
from src.reporting.simple_pdf_builder import build_simple_pdf
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path

REPORT_ROOT = Path("data/editorial")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_editorial_report(db: Session, submission_id: str) -> dict:
    """构建不含原稿正文的编辑预审规范 JSON。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise ValueError(f"EditorialSubmission {submission_id} not found")
    paper = db.get(Paper, submission.paper_id)
    task = db.get(EvaluationTask, submission.evaluation_task_id)
    if paper is None or task is None:
        raise ValueError("编辑报告所需数据不完整")

    scores = (
        db.query(DimensionScore)
        .filter(
            DimensionScore.task_id == task.id,
            DimensionScore.round_number == task.final_round,
        )
        .order_by(DimensionScore.dimension_key, DimensionScore.model_name)
        .all()
    )
    reliability = (
        db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .order_by(ReliabilityResult.dimension_key)
        .all()
    )
    position = (
        db.query(PositionAssessment)
        .filter(PositionAssessment.submission_id == submission.id)
        .order_by(PositionAssessment.version.desc())
        .first()
    )
    opinions = (
        db.query(EditorialOpinion)
        .filter(EditorialOpinion.submission_id == submission.id)
        .order_by(
            EditorialOpinion.opinion_type,
            EditorialOpinion.version,
            EditorialOpinion.sequence,
        )
        .all()
    )
    decisions = (
        db.query(EditorialDecision)
        .filter(EditorialDecision.submission_id == submission.id)
        .order_by(EditorialDecision.version)
        .all()
    )
    policy = load_editorial_policy(submission.policy_key)
    provider_names = json.loads(task.provider_names or "[]")
    framework = load_framework(task.framework_path or str(resolve_framework_path()))
    six_dimension_summary = build_six_dimension_summary(
        scores,
        reliability,
        policy,
        provider_names,
        [(dimension.key, dimension.name_zh) for dimension in framework.dimensions],
    )
    expert_reviews = []
    for review in (
        db.query(ExpertReview)
        .filter(ExpertReview.task_id == task.id)
        .order_by(ExpertReview.created_at)
        .all()
    ):
        comments = (
            db.query(ReviewComment)
            .filter(ReviewComment.review_id == review.id)
            .order_by(ReviewComment.dimension_key)
            .all()
        )
        expert_reviews.append(
            {
                "status": review.status,
                "blind_submitted_at": (
                    review.blind_submitted_at.isoformat()
                    if review.blind_submitted_at
                    else None
                ),
                "completed_at": (
                    review.completed_at.isoformat() if review.completed_at else None
                ),
                "comments": [
                    {
                        "dimension_key": item.dimension_key,
                        "expert_score": item.expert_score,
                        "reason": item.reason,
                        "statement_decisions": item.statement_decisions,
                        "comparison_reason": item.comparison_reason,
                    }
                    for item in comments
                ],
            }
        )
    return {
        "schema_version": "editorial-report-v3",
        "submission": {
            "id": submission.id,
            "unit_id": submission.unit_id,
            "external_manuscript_id": submission.external_manuscript_id,
            "title": submission.title,
            "status": submission.status,
            "responsible_editor_id": submission.responsible_editor_id,
        },
        "policy": {
            "key": submission.policy_key,
            "version": submission.policy_version,
        },
        "gates": {
            "anonymization_status": submission.anonymization_status,
            "anonymization_result": submission.anonymization_result,
            "formal_check_status": submission.formal_check_status,
            "formal_check_result": submission.formal_check_result,
            "precheck_status": paper.precheck_status,
            "precheck_result": paper.precheck_result,
            "journal_fit_status": submission.fit_status,
            "journal_fit_result": submission.fit_result,
        },
        "evaluation": {
            "display_order": ["five_axis", "six_dimension"],
            "framework_id": task.framework_id,
            "final_round": task.final_round,
            "cross_review_enabled": task.cross_review_enabled,
            "manual_review_requested": task.manual_review_requested,
            "aggregate": paper.aggregate_result,
            "ccb_summary": build_ccb_summary(paper.aggregate_result),
            "six_dimension_scores": [
                {
                    "dimension_key": row.dimension_key,
                    "model_name": row.model_name,
                    "score": row.score,
                    "band": (row.structured_payload or {}).get("band")
                    or (row.structured_payload or {}).get("revised_band"),
                    "evidence_quotes": row.evidence_quotes,
                    "analysis": row.analysis,
                }
                for row in scores
            ],
            "reliability": [
                {
                    "dimension_key": row.dimension_key,
                    "mean_score": row.mean_score,
                    "std_score": row.std_score,
                    "requires_expert_review": row.std_score > 8,
                }
                for row in reliability
            ],
            "position_assessment": position.result_data if position else None,
            "position_summary": build_position_summary(
                position.result_data if position else None,
                precheck_result=paper.precheck_result,
            ),
            "six_dimension_summary": six_dimension_summary,
        },
        "ai_opinions": [
            {
                "id": row.id,
                "type": row.opinion_type,
                "version": row.version,
                "sequence": row.sequence,
                "content": row.content,
                "label": (
                    "智能辅助意见" if row.opinion_type.startswith("ai_") else "编辑意见"
                ),
                "locked": row.is_locked,
            }
            for row in opinions
        ],
        "recommendation": {
            "state": submission.recommendation_state,
            "candidate_decision": (
                submission.internal_candidate_decision
                if submission.recommendation_state == "ready"
                else None
            ),
        },
        "editorial_decisions": [
            {
                "id": row.id,
                "version": row.version,
                "decision_stage": row.decision_stage,
                "final_decision": row.final_decision,
                "suggested_decision": row.suggested_decision,
                "rationale": row.rationale,
                "bypassed_expert_gate": row.bypassed_expert_gate,
                "actor_id": row.actor_id,
                "locked": row.is_locked,
            }
            for row in decisions
        ],
        "expert_reviews": expert_reviews,
    }


def _pdf_payload(report: dict) -> dict:
    dimensions = report["evaluation"]["six_dimension_summary"]["dimensions"]
    synthesis = next(
        (
            item["content"]
            for item in report["ai_opinions"]
            if item["type"] == "ai_synthesis"
        ),
        {},
    )
    ccb = report["evaluation"].get("ccb_summary") or {}
    position = report["evaluation"].get("position_summary")
    expert_comments = [
        comment["reason"]
        for review in report.get("expert_reviews", [])
        for comment in review.get("comments", [])
        if comment.get("reason")
    ]
    return {
        "title": report["submission"]["title"],
        "weighted_total": ccb.get("final_score", 0),
        "ccb_summary": ccb,
        "position_summary": position,
        "conclusion": synthesis.get("synthesis") or synthesis.get("summary"),
        "dimensions": [
            {
                "name_zh": item["dimension_name"],
                "ai": {"mean_score": item["mean_score"]},
                "summary": (
                    f"标准差 {item['std_score']:.2f}，{item['difference_label']}"
                ),
            }
            for item in dimensions
        ],
        "expert_conclusion": "；".join(expert_comments) or None,
    }


def generate_editorial_report(db: Session, submission_id: str) -> tuple[int, dict]:
    """追加一版不可变 JSON 与 PDF，并更新当前报告版本指针。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise ValueError(f"EditorialSubmission {submission_id} not found")
    report = build_editorial_report(db, submission_id)
    version = submission.current_report_version + 1
    directory = REPORT_ROOT / submission.id
    directory.mkdir(parents=True, exist_ok=True)

    json_content = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8")
    json_path = directory / f"report-v{version}.json"
    json_path.write_bytes(json_content)
    pdf_content = build_simple_pdf(_pdf_payload(report))
    pdf_path = directory / f"report-v{version}.pdf"
    pdf_path.write_bytes(pdf_content)

    db.add_all(
        [
            EditorialDocument(
                submission_id=submission.id,
                kind="report_json",
                version=version,
                file_path=str(json_path),
                sha256=_sha256(json_content),
            ),
            EditorialDocument(
                submission_id=submission.id,
                kind="report_pdf",
                version=version,
                file_path=str(pdf_path),
                sha256=_sha256(pdf_content),
            ),
        ]
    )
    submission.current_report_version = version
    db.add(submission)
    db.commit()
    return version, report
