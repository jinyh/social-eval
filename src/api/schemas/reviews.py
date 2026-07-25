from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewQueueItem(BaseModel):
    task_id: str
    paper_id: str
    paper_title: str | None
    paper_status: str | None
    task_status: str
    low_confidence_dimensions: list[str]


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]


class AssignExpertsRequest(BaseModel):
    expert_ids: list[str] = Field(min_length=1)


class AssignExpertsResponse(BaseModel):
    assigned_count: int
    review_ids: list[str]


class MyReviewItem(BaseModel):
    review_id: str
    task_id: str
    paper_id: str
    paper_title: str | None
    status: str
    review_stage: str
    required_dimensions: list[str]


class MyReviewsResponse(BaseModel):
    items: list[MyReviewItem]


class ReviewCommentInput(BaseModel):
    dimension_key: str
    ai_score: float | None = Field(default=None, ge=0, le=100)
    expert_score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)
    statement_decisions: dict[str, str] | None = None


class BlindReviewSubmitRequest(BaseModel):
    comments: list[ReviewCommentInput] = Field(min_length=1)


class ExpertComparisonInput(BaseModel):
    dimension_key: str
    statement_decisions: dict[str, str] = Field(default_factory=dict)
    comparison_reason: str = Field(default="", max_length=5000)


class SubmitReviewRequest(BaseModel):
    comparisons: list[ExpertComparisonInput] = Field(default_factory=list)


class SubmitReviewResponse(BaseModel):
    review_id: str
    status: str
