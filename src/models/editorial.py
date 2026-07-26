from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.time import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EditorialUnit(Base):
    __tablename__ = "editorial_units"
    __table_args__ = (UniqueConstraint("journal_id", "code", name="uq_unit_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    journal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("journals.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str] = mapped_column(String(100), default="law", nullable=False)
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    trial_policy_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "editorial_policy_versions.id",
            name="fk_unit_trial_policy_version",
            use_alter=True,
        ),
        nullable=True,
    )
    active_policy_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "editorial_policy_versions.id",
            name="fk_unit_active_policy_version",
            use_alter=True,
        ),
        nullable=True,
    )
    rollout_state: Mapped[str] = mapped_column(
        String(20), default="shadow", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class EditorialPolicyVersion(Base):
    """编辑单元不可变的期刊适配与模型策略快照。"""

    __tablename__ = "editorial_policy_versions"
    __table_args__ = (
        UniqueConstraint("unit_id", "version", name="uq_unit_policy_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_units.id"), nullable=False
    )
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    based_on_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("editorial_policy_versions.id"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    activated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EditorialUnitMembership(Base):
    __tablename__ = "editorial_unit_memberships"
    __table_args__ = (UniqueConstraint("unit_id", "user_id", name="uq_unit_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_units.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    membership_role: Mapped[str] = mapped_column(
        String(30), default="editor", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EditorialSubmission(Base):
    __tablename__ = "editorial_submissions"
    __table_args__ = (
        UniqueConstraint(
            "unit_id",
            "external_manuscript_id",
            name="uq_unit_external_manuscript",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_units.id"), nullable=False
    )
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id"), nullable=False, unique=True
    )
    evaluation_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_tasks.id"), nullable=True, unique=True
    )
    external_manuscript_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    responsible_editor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    anonymization_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    anonymization_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formal_check_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    formal_check_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    formal_check_override_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    precheck_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fit_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fit_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_state: Mapped[str] = mapped_column(
        String(20), default="shadow", nullable=False
    )
    internal_candidate_decision: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("editorial_policy_versions.id"), nullable=True
    )
    current_report_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    retention_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retention_hold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EditorialDocument(Base):
    __tablename__ = "editorial_documents"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "kind", "version", name="uq_submission_document_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_submissions.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PositionAssessment(Base):
    __tablename__ = "position_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_submissions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EditorialOpinion(Base):
    __tablename__ = "editorial_opinions"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "opinion_type",
            "version",
            "sequence",
            name="uq_editorial_opinion_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_submissions.id"), nullable=False
    )
    opinion_type: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EditorialDecision(Base):
    __tablename__ = "editorial_decisions"
    __table_args__ = (
        UniqueConstraint("submission_id", "version", name="uq_decision_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("editorial_submissions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_stage: Mapped[str] = mapped_column(
        String(30), default="pre_review", nullable=False
    )
    suggested_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    final_decision: Mapped[str] = mapped_column(String(30), nullable=False)
    recommendation_state: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    bypassed_expert_gate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reopened_from_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("editorial_decisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EmailDelivery(Base):
    """不保存稿件内容的持久化邮件发件箱。"""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_email_delivery_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    template_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class ValidationRun(Base):
    """编辑单元校准、冻结测试和最终验证的签字真源。"""

    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("editorial_units.id"), nullable=True
    )
    validation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    framework_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_set_version: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("editorial_policy_versions.id"), nullable=True
    )
    sample_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    signed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    signer_membership_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
