from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.email import send_editorial_event_email
from src.core.time import utc_now
from src.models.editorial import EditorialSubmission, Notification
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.models.user import User
from src.reporting.versioning import generate_reports_for_task


def required_review_dimensions(db: Session, task: EvaluationTask) -> list[str]:
    """返回必须复核的六维；非六维门禁触发时回退为全部六维。"""

    rows = (
        db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .order_by(ReliabilityResult.dimension_key)
        .all()
    )
    required = [row.dimension_key for row in rows if row.std_score > 8]
    return required or [row.dimension_key for row in rows]


def submit_blind_review(
    db: Session,
    *,
    review_id: str,
    expert_id: str,
    comments: list[dict],
) -> ExpertReview:
    """锁定专家独立评分，再开放智能结果对照。"""

    review = db.get(ExpertReview, review_id)
    if review is None or review.expert_id != expert_id:
        raise ValueError("未找到专家复核任务")
    if review.blind_submitted_at is not None:
        raise ValueError("独立评阅已经提交并锁定")
    task = db.get(EvaluationTask, review.task_id)
    if task is None:
        raise ValueError("未找到评价任务")
    required = set(required_review_dimensions(db, task))
    submitted = {str(item["dimension_key"]) for item in comments}
    missing = sorted(required - submitted)
    if missing:
        raise ValueError(f"尚未完成必须复核维度：{'、'.join(missing)}")

    reliability = {
        row.dimension_key: row
        for row in db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .all()
    }
    db.query(ReviewComment).filter(ReviewComment.review_id == review.id).delete()
    for comment in comments:
        dimension_key = str(comment["dimension_key"])
        row = reliability.get(dimension_key)
        if row is None:
            raise ValueError(f"未知复核维度：{dimension_key}")
        db.add(
            ReviewComment(
                review_id=review.id,
                dimension_key=dimension_key,
                ai_score=row.mean_score,
                expert_score=comment["expert_score"],
                reason=comment["reason"],
                statement_decisions=comment.get("statement_decisions"),
            )
        )

    now = utc_now()
    review.status = "comparison"
    review.blind_submitted_at = now
    review.ai_revealed_at = now
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def submit_expert_comparison(
    db: Session,
    *,
    review_id: str,
    expert_id: str,
    comparisons: list[dict],
) -> ExpertReview:
    """保存对四模型意见的逐项态度并完成专家复核。"""

    review = db.get(ExpertReview, review_id)
    if review is None or review.expert_id != expert_id:
        raise ValueError("未找到专家复核任务")
    if review.blind_submitted_at is None:
        raise ValueError("必须先提交独立评阅")
    if review.status == "submitted":
        raise ValueError("专家复核已经完成")

    comments = {
        row.dimension_key: row
        for row in db.query(ReviewComment)
        .filter(ReviewComment.review_id == review.id)
        .all()
    }
    for comparison in comparisons:
        dimension_key = str(comparison["dimension_key"])
        comment = comments.get(dimension_key)
        if comment is None:
            raise ValueError(f"未知复核维度：{dimension_key}")
        decisions = comparison.get("statement_decisions") or {}
        invalid = {
            value
            for value in decisions.values()
            if value not in {"accept", "reject", "neutral"}
        }
        if invalid:
            raise ValueError("具体判断只能选择认可、不认可或无意见")
        if (
            "reject" in decisions.values()
            and not str(comparison.get("comparison_reason", "")).strip()
        ):
            raise ValueError("不认可智能判断时必须填写对照说明")
        comment.statement_decisions = decisions
        comment.comparison_reason = str(comparison.get("comparison_reason", "")).strip()
        db.add(comment)

    review.status = "submitted"
    review.completed_at = utc_now()
    db.add(review)
    db.commit()
    db.refresh(review)
    _complete_task_if_ready(db, review)
    return review


def _complete_task_if_ready(db: Session, review: ExpertReview) -> None:
    task = db.get(EvaluationTask, review.task_id)
    paper = db.get(Paper, task.paper_id) if task else None
    if task is None or paper is None:
        raise ValueError("未找到专家复核对应的评价任务")

    pending_reviews = (
        db.query(ExpertReview)
        .filter(
            ExpertReview.task_id == task.id,
            ExpertReview.status != "submitted",
        )
        .count()
    )
    if pending_reviews == 0:
        task.status = "completed"
        task.manual_review_requested = False
        paper.status = "completed"
    else:
        task.status = "reviewing"
        paper.status = "reviewing"

    db.add(task)
    db.add(paper)
    editorial_submission = (
        db.query(EditorialSubmission)
        .filter(EditorialSubmission.evaluation_task_id == task.id)
        .first()
    )
    if editorial_submission is not None and pending_reviews == 0:
        editorial_submission.status = "awaiting_editor"
        db.add(editorial_submission)
    if (
        editorial_submission is not None
        and editorial_submission.responsible_editor_id is not None
    ):
        db.add(
            Notification(
                user_id=editorial_submission.responsible_editor_id,
                event_type="expert_review_submitted",
                object_type="editorial_submission",
                object_id=editorial_submission.id,
                payload={"submission_id": editorial_submission.id},
            )
        )
        editor = db.get(User, editorial_submission.responsible_editor_id)
        if editor is not None:
            send_editorial_event_email(
                db=db,
                recipient_email=editor.email,
                submission_id=editorial_submission.id,
                event_type="expert_review_submitted",
            )
    db.commit()
    generate_reports_for_task(db, task.id)


def submit_expert_review(
    db: Session,
    *,
    review_id: str,
    expert_id: str,
    comments: list[dict],
) -> ExpertReview:
    """兼容内部调用：依次完成独立评阅和空对照提交。"""

    review = submit_blind_review(
        db,
        review_id=review_id,
        expert_id=expert_id,
        comments=comments,
    )
    return submit_expert_comparison(
        db,
        review_id=review.id,
        expert_id=expert_id,
        comparisons=[],
    )
