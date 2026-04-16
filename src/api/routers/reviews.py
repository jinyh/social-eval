from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.api.auth.dependencies import get_current_user, require_roles
from src.api.schemas.reviews import (
    AssignExpertsRequest,
    AssignExpertsResponse,
    MyReviewItem,
    MyReviewsResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    SubmitReviewRequest,
    SubmitReviewResponse,
)
from src.core.database import get_db
from src.models.review import ExpertReview
from src.models.user import User
from src.review.assignment import assign_experts
from src.review.queue import list_review_queue
from src.review.submission import submit_expert_review

router = APIRouter()


@router.get("/queue", response_model=ReviewQueueResponse)
def get_review_queue(
    _: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    items = [ReviewQueueItem(**item) for item in list_review_queue(db)]
    return ReviewQueueResponse(items=items)


@router.post("/{task_id}/assign", response_model=AssignExpertsResponse, status_code=status.HTTP_201_CREATED)
def assign_reviewers(
    task_id: str,
    payload: AssignExpertsRequest,
    request: Request,
    _: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> AssignExpertsResponse:
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
    rows = db.query(ExpertReview).filter(ExpertReview.expert_id == current_user.id).all()
    return MyReviewsResponse(
        items=[MyReviewItem(review_id=row.id, task_id=row.task_id, status=row.status) for row in rows]
    )


@router.post("/{review_id}/submit", response_model=SubmitReviewResponse)
def submit_review(
    review_id: str,
    payload: SubmitReviewRequest,
    current_user: User = Depends(require_roles("expert")),
    db: Session = Depends(get_db),
) -> SubmitReviewResponse:
    try:
        review = submit_expert_review(
            db,
            review_id=review_id,
            expert_id=current_user.id,
            comments=[comment.model_dump() for comment in payload.comments],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SubmitReviewResponse(review_id=review.id, status=review.status)
