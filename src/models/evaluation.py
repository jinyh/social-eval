import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base
from src.core.time import utc_now


class EvaluationTask(Base):
    __tablename__ = "evaluation_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id"), nullable=False
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("batch_tasks.id"), nullable=True
    )
    framework_id: Mapped[str] = mapped_column(String(36), nullable=False)
    framework_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    input_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_names: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # JSON 字符串，如 ["openai","anthropic"]
    model_set_version: Mapped[str] = mapped_column(
        String(100), default="six-dimension-v1", nullable=False
    )
    run_role: Mapped[str] = mapped_column(
        String(30), default="production", nullable=False
    )
    comparison_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending/processing/completed/failed
    manual_review_requested: Mapped[bool] = mapped_column(default=False)
    cross_review_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    final_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    failure_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class EvaluationWorkUnit(Base):
    """可恢复评价任务中的一个唯一逻辑工作单元。"""

    __tablename__ = "evaluation_work_units"
    __table_args__ = (
        UniqueConstraint("task_id", "unit_key", name="uq_evaluation_work_unit"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_tasks.id"), nullable=False
    )
    unit_key: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DimensionScore(Base):
    __tablename__ = "dimension_scores"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_tasks.id"), nullable=False
    )
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_quotes: Mapped[dict] = mapped_column(JSON, nullable=True)
    analysis: Mapped[str] = mapped_column(Text, nullable=True)
    structured_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AICallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_tasks.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    call_type: Mapped[str] = mapped_column(
        String(50), default="dimension_score", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
