import uuid
from datetime import datetime
from sqlalchemy import String, Float, Text, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class EvaluationTask(Base):
    __tablename__ = "evaluation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id"), nullable=False)
    framework_id: Mapped[str] = mapped_column(String(36), nullable=False)
    framework_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_names: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON 字符串，如 ["openai","anthropic"]
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/completed/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DimensionScore(Base):
    __tablename__ = "dimension_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_tasks.id"), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_quotes: Mapped[dict] = mapped_column(JSON, nullable=True)
    analysis: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AICallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("evaluation_tasks.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
