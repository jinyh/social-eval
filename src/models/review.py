import uuid
from datetime import datetime
from sqlalchemy import JSON, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base
from src.core.time import utc_now


class ExpertReview(Base):
    __tablename__ = "expert_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_tasks.id"), nullable=False
    )
    expert_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending/submitted/returned
    version: Mapped[int] = mapped_column(default=1)
    blind_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ai_revealed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expert_reviews.id"), nullable=False
    )
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    ai_score: Mapped[float] = mapped_column(Float, nullable=False)
    expert_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    statement_decisions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comparison_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
