import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, JSON, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base
from src.core.time import utc_now


class ReliabilityResult(Base):
    __tablename__ = "reliability_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_tasks.id"), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    mean_score: Mapped[float] = mapped_column(Float, nullable=False)
    std_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_high_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_scores: Mapped[dict] = mapped_column(JSON, nullable=True)
    confidence_level: Mapped[str] = mapped_column(String(20), default="high", nullable=False)
    requires_evidence_supplement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    divergence_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
