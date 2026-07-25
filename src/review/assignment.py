from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.editorial import EditorialSubmission, Notification
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.review import ExpertReview
from src.models.user import User


def assign_experts(
    db: Session,
    *,
    task_id: str,
    expert_ids: list[str],
    email_sender,
) -> dict:
    task = db.get(EvaluationTask, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    paper = db.get(Paper, task.paper_id)
    if paper is None:
        raise ValueError(f"Paper for task {task_id} not found")

    assigned_reviews = []
    editorial_submission = (
        db.query(EditorialSubmission)
        .filter(EditorialSubmission.evaluation_task_id == task.id)
        .first()
    )
    for expert_id in expert_ids:
        expert = db.get(User, expert_id)
        if expert is None or expert.role != "expert":
            raise ValueError(f"Expert {expert_id} not found")
        existing = (
            db.query(ExpertReview)
            .filter(
                ExpertReview.task_id == task.id,
                ExpertReview.expert_id == expert.id,
                ExpertReview.status != "returned",
            )
            .first()
        )
        if existing is not None:
            assigned_reviews.append(existing)
            continue
        review = ExpertReview(
            task_id=task.id, expert_id=expert.id, status="pending", version=1
        )
        db.add(review)
        db.flush()
        db.add(
            Notification(
                user_id=expert.id,
                event_type="expert_review_assigned",
                object_type="evaluation_task",
                object_id=task.id,
                payload={"task_id": task.id, "review_id": review.id},
            )
        )
        db.commit()
        db.refresh(review)
        assigned_reviews.append(review)
        email_sender(
            db=db,
            expert_email=expert.email,
            task_id=task.id,
            paper_title=(
                f"系统稿号 {editorial_submission.id}"
                if editorial_submission
                else paper.title or paper.original_filename
            ),
            summary="有一项专家复核任务等待处理。",
        )

    task.status = "reviewing"
    task.manual_review_requested = True
    paper.status = "reviewing"
    db.add(task)
    db.add(paper)
    db.commit()
    return {
        "assigned_count": len(assigned_reviews),
        "review_ids": [review.id for review in assigned_reviews],
    }
