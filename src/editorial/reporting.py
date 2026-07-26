from __future__ import annotations

import hashlib
import json
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.core.time import utc_now
from src.editorial.policy import resolve_submission_policy
from src.editorial.presentation import (
    build_ccb_summary,
    build_position_summary,
    build_six_dimension_summary,
    localize_synthesis_payload,
)
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path
from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialOpinion,
    EditorialSubmission,
    EditorialUnit,
    Journal,
    PositionAssessment,
)
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.reporting.editorial_pdf_builder import build_editorial_pdf

REPORT_ROOT = Path("data/editorial")

_DECISION_LABELS = {
    "decline_without_review": "不送外审",
    "revise_resubmit": "修改后重投",
    "send_external_review": "送外审",
    "priority_external_review": "优先送外审",
    "reject": "退稿",
    "major_revision": "重大修改",
    "minor_accept": "小修后录用",
    "direct_accept": "直接录用",
}

_STAGE_LABELS = {
    "pre_review": "编辑预审",
    "final": "期刊终审",
    "legacy": "历史预审记录",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_editorial_report(
    db: Session,
    submission_id: str,
    *,
    report_version: int | None = None,
) -> dict:
    """构建不含原稿正文的编辑预审规范 JSON。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise ValueError(f"EditorialSubmission {submission_id} not found")
    paper = db.get(Paper, submission.paper_id)
    task = db.get(EvaluationTask, submission.evaluation_task_id)
    if paper is None or task is None:
        raise ValueError("编辑报告所需数据不完整")
    unit = db.get(EditorialUnit, submission.unit_id)
    journal = db.get(Journal, unit.journal_id) if unit else None
    next_version = report_version or submission.current_report_version + 1
    generated_at = utc_now().replace(tzinfo=timezone.utc)

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
    policy = resolve_submission_policy(db, submission)
    provider_names = json.loads(task.provider_names or "[]")
    framework = load_framework(task.framework_path or str(resolve_framework_path()))
    six_dimension_summary = build_six_dimension_summary(
        scores,
        reliability,
        policy,
        provider_names,
        [(dimension.key, dimension.name_zh) for dimension in framework.dimensions],
    )
    dimension_labels = {
        dimension.key: dimension.name_zh for dimension in framework.dimensions
    }
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
                        "dimension_name": dimension_labels.get(
                            item.dimension_key,
                            "补充维度",
                        ),
                        "expert_score": item.expert_score,
                        "reason": item.reason,
                        "statement_decisions": item.statement_decisions,
                        "comparison_reason": item.comparison_reason,
                    }
                    for item in comments
                ],
            }
        )
    candidate_decision = (
        submission.internal_candidate_decision
        if submission.recommendation_state == "ready"
        else None
    )
    recommendation_label = (
        _DECISION_LABELS.get(candidate_decision, "建议状态待确认")
        if candidate_decision
        else (
            "建议已扣留，需人工处理"
            if submission.recommendation_state == "withheld"
            else "试运行结果，不直接形成编辑决定"
        )
    )
    return {
        "schema_version": "editorial-report-v4",
        "report_metadata": {
            "report_version": next_version,
            "generated_at": generated_at.isoformat(),
            "generated_at_zh": generated_at.astimezone(
                ZoneInfo("Asia/Shanghai")
            ).strftime("%Y年%m月%d日 %H:%M"),
            "journal_name": journal.name if journal else None,
            "unit_name": unit.name if unit else None,
            "framework_version": task.framework_id,
            "model_set_version": task.model_set_version,
            "review_protocol_version": task.review_protocol_version,
            "review_protocol_label": (
                "四模型匿名互评"
                if task.review_protocol_version == "six_dimension_peer_review"
                else "分组交叉复核"
            ),
            "policy_version": submission.policy_version,
        },
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
            "display_order": [
                "ai_synthesis",
                "five_axis",
                "six_dimension",
                "expert_review",
                "editorial_decision",
            ],
            "framework_id": task.framework_id,
            "final_round": task.final_round,
            "cross_review_enabled": task.cross_review_enabled,
            "review_protocol_version": task.review_protocol_version,
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
                "content": (
                    localize_synthesis_payload(row.content)
                    if row.opinion_type == "ai_synthesis"
                    else row.content
                ),
                "label": (
                    "智能辅助意见" if row.opinion_type.startswith("ai_") else "编辑意见"
                ),
                "locked": row.is_locked,
            }
            for row in opinions
        ],
        "recommendation": {
            "state": submission.recommendation_state,
            "candidate_decision": candidate_decision,
            "display_label": recommendation_label,
        },
        "editorial_decisions": [
            {
                "id": row.id,
                "version": row.version,
                "decision_stage": row.decision_stage,
                "stage_label": _STAGE_LABELS.get(
                    row.decision_stage,
                    "历史预审记录",
                ),
                "final_decision": row.final_decision,
                "decision_label": _DECISION_LABELS.get(
                    row.final_decision,
                    "决定待确认",
                ),
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


def generate_editorial_report(db: Session, submission_id: str) -> tuple[int, dict]:
    """追加一版不可变 JSON 与 PDF，并更新当前报告版本指针。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise ValueError(f"EditorialSubmission {submission_id} not found")
    version = submission.current_report_version + 1
    report = build_editorial_report(
        db,
        submission_id,
        report_version=version,
    )
    directory = REPORT_ROOT / submission.id
    directory.mkdir(parents=True, exist_ok=True)

    json_content = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8")
    pdf_content = build_editorial_pdf(report)

    json_path = directory / f"report-v{version}.json"
    json_path.write_bytes(json_content)
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
