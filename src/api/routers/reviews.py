from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.reviews import (
    AssignExpertsRequest,
    AssignExpertsResponse,
    BlindReviewSubmitRequest,
    MyReviewItem,
    MyReviewsResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    SubmitReviewRequest,
    SubmitReviewResponse,
)
from src.core.database import get_db
from src.editorial.access import accessible_unit_ids, editor_can_access_task
from src.models.editorial import EditorialDocument, EditorialSubmission
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.review import ExpertReview
from src.models.user import User
from src.review.assignment import assign_experts
from src.review.queue import list_review_queue
from src.review.submission import (
    required_review_dimensions,
    submit_blind_review,
    submit_expert_comparison,
)

router = APIRouter()


@router.get("/queue", response_model=ReviewQueueResponse)
def get_review_queue(
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    allowed_task_ids = None
    if current_user.role == "editor":
        editorial_task_ids = {
            row[0]
            for row in db.query(EditorialSubmission.evaluation_task_id)
            .filter(EditorialSubmission.evaluation_task_id.is_not(None))
            .all()
        }
        allowed_editorial_task_ids = {
            row[0]
            for row in db.query(EditorialSubmission.evaluation_task_id)
            .filter(
                EditorialSubmission.unit_id.in_(accessible_unit_ids(db, current_user)),
                EditorialSubmission.evaluation_task_id.is_not(None),
            )
            .all()
        }
        all_task_ids = {row[0] for row in db.query(EvaluationTask.id).all()}
        allowed_task_ids = (
            all_task_ids - editorial_task_ids
        ) | allowed_editorial_task_ids
    items = [
        ReviewQueueItem(**item)
        for item in list_review_queue(db, allowed_task_ids=allowed_task_ids)
    ]
    return ReviewQueueResponse(items=items)


@router.post(
    "/{task_id}/assign",
    response_model=AssignExpertsResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_reviewers(
    task_id: str,
    payload: AssignExpertsRequest,
    request: Request,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> AssignExpertsResponse:
    if current_user.role == "editor" and not editor_can_access_task(
        db, current_user, task_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    email_sender = getattr(request.app.state, "email_sender", None)
    result = assign_experts(
        db,
        task_id=task_id,
        expert_ids=payload.expert_ids,
        email_sender=email_sender,
    )
    return AssignExpertsResponse(**result)


@router.get("/mine", response_model=MyReviewsResponse)
def list_my_reviews(
    current_user: User = Depends(require_roles("expert")),
    db: Session = Depends(get_db),
) -> MyReviewsResponse:
    rows = (
        db.query(ExpertReview, EvaluationTask, Paper)
        .join(EvaluationTask, ExpertReview.task_id == EvaluationTask.id)
        .join(Paper, EvaluationTask.paper_id == Paper.id)
        .filter(ExpertReview.expert_id == current_user.id)
        .all()
    )
    return MyReviewsResponse(
        items=[
            MyReviewItem(
                review_id=review.id,
                task_id=review.task_id,
                paper_id=paper.id,
                paper_title=paper.title or paper.original_filename,
                status=review.status,
                review_stage=(
                    "blind"
                    if review.blind_submitted_at is None
                    else ("comparison" if review.status != "submitted" else "completed")
                ),
                required_dimensions=required_review_dimensions(db, task),
            )
            for review, task, paper in rows
        ]
    )


@router.get("/{review_id}/document")
def get_anonymized_review_document(
    review_id: str,
    current_user: User = Depends(require_roles("expert")),
    db: Session = Depends(get_db),
):
    """专家只能访问与本人任务关联的匿名稿。"""

    review = db.get(ExpertReview, review_id)
    if review is None or review.expert_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到专家复核任务")
    submission = (
        db.query(EditorialSubmission)
        .filter(EditorialSubmission.evaluation_task_id == review.task_id)
        .first()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到匿名稿")
    document = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind == "anonymized",
        )
        .order_by(EditorialDocument.version.desc())
        .first()
    )
    if document is None or not Path(document.file_path).exists():
        raise HTTPException(status_code=404, detail="匿名稿文件不存在")
    return FileResponse(
        document.file_path,
        filename="匿名稿.txt",
        media_type="text/plain",
    )


@router.post("/{review_id}/blind-submit", response_model=SubmitReviewResponse)
def submit_blind_assessment(
    review_id: str,
    payload: BlindReviewSubmitRequest,
    current_user: User = Depends(require_roles("expert")),
    db: Session = Depends(get_db),
) -> SubmitReviewResponse:
    try:
        review = submit_blind_review(
            db,
            review_id=review_id,
            expert_id=current_user.id,
            comments=[comment.model_dump() for comment in payload.comments],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SubmitReviewResponse(review_id=review.id, status=review.status)


@router.post("/{review_id}/submit", response_model=SubmitReviewResponse)
def submit_review(
    review_id: str,
    payload: SubmitReviewRequest,
    current_user: User = Depends(require_roles("expert")),
    db: Session = Depends(get_db),
) -> SubmitReviewResponse:
    try:
        review = submit_expert_comparison(
            db,
            review_id=review_id,
            expert_id=current_user.id,
            comparisons=[comparison.model_dump() for comparison in payload.comparisons],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return SubmitReviewResponse(review_id=review.id, status=review.status)
