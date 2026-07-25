"""add editorial workflow

Revision ID: 010
Revises: 009
Create Date: 2026-07-24
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_tasks",
        sa.Column("input_file_path", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("provider_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="success",
        ),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("failure_detail", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "journals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "editorial_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("discipline", sa.String(length=100), nullable=False),
        sa.Column("policy_key", sa.String(length=120), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("rollout_state", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_id", "code", name="uq_unit_code"),
    )
    now = datetime(2026, 7, 24)
    journals = sa.table(
        "journals",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )
    units = sa.table(
        "editorial_units",
        sa.column("id", sa.String),
        sa.column("journal_id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("discipline", sa.String),
        sa.column("policy_key", sa.String),
        sa.column("policy_version", sa.String),
        sa.column("rollout_state", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    journal_rows = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "code": "jiaoda-law",
            "name": "交大法学",
            "is_active": True,
            "created_at": now,
        },
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "code": "academic-monthly",
            "name": "学术月刊",
            "is_active": True,
            "created_at": now,
        },
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "code": "oriental-law",
            "name": "东方法学",
            "is_active": True,
            "created_at": now,
        },
    ]
    unit_rows = [
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "journal_id": journal_rows[0]["id"],
            "code": "default",
            "name": "交大法学编辑部",
            "discipline": "law",
            "policy_key": "jiaoda-law-v1",
            "policy_version": "1.0",
            "rollout_state": "shadow",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "00000000-0000-0000-0000-000000000102",
            "journal_id": journal_rows[1]["id"],
            "code": "law",
            "name": "学术月刊法学板块",
            "discipline": "law",
            "policy_key": "academic-monthly-law-v1",
            "policy_version": "1.0",
            "rollout_state": "shadow",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "00000000-0000-0000-0000-000000000103",
            "journal_id": journal_rows[2]["id"],
            "code": "default",
            "name": "东方法学编辑部",
            "discipline": "law",
            "policy_key": "oriental-law-v1",
            "policy_version": "1.0",
            "rollout_state": "shadow",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]
    op.bulk_insert(journals, journal_rows)
    op.bulk_insert(units, unit_rows)
    op.create_table(
        "editorial_unit_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("membership_role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["editorial_units.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id", "user_id", name="uq_unit_member"),
    )
    op.create_table(
        "editorial_submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_task_id", sa.String(length=36), nullable=True),
        sa.Column("external_manuscript_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("responsible_editor_id", sa.String(length=36), nullable=True),
        sa.Column("anonymization_status", sa.String(length=30), nullable=False),
        sa.Column("anonymization_result", sa.JSON(), nullable=True),
        sa.Column("precheck_override_reason", sa.Text(), nullable=True),
        sa.Column("fit_status", sa.String(length=30), nullable=True),
        sa.Column("fit_result", sa.JSON(), nullable=True),
        sa.Column("fit_override_reason", sa.Text(), nullable=True),
        sa.Column("recommendation_state", sa.String(length=20), nullable=False),
        sa.Column("internal_candidate_decision", sa.String(length=30), nullable=True),
        sa.Column("policy_key", sa.String(length=120), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("current_report_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["evaluation_task_id"], ["evaluation_tasks.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["responsible_editor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["editorial_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_task_id"),
        sa.UniqueConstraint("paper_id"),
        sa.UniqueConstraint(
            "unit_id",
            "external_manuscript_id",
            name="uq_unit_external_manuscript",
        ),
    )
    op.create_table(
        "editorial_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["editorial_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "kind",
            "version",
            name="uq_submission_document_version",
        ),
    )
    op.create_table(
        "position_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["editorial_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "editorial_opinions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("opinion_type", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["editorial_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "opinion_type",
            "version",
            "sequence",
            name="uq_editorial_opinion_version",
        ),
    )
    op.create_table(
        "editorial_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("suggested_decision", sa.String(length=30), nullable=True),
        sa.Column("final_decision", sa.String(length=30), nullable=False),
        sa.Column("recommendation_state", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("bypassed_expert_gate", sa.Boolean(), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("reopened_from_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reopened_from_id"], ["editorial_decisions.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["editorial_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "version", name="uq_decision_version"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("object_type", sa.String(length=50), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("editorial_decisions")
    op.drop_table("editorial_opinions")
    op.drop_table("position_assessments")
    op.drop_table("editorial_documents")
    op.drop_table("editorial_submissions")
    op.drop_table("editorial_unit_memberships")
    op.drop_table("editorial_units")
    op.drop_table("journals")
    op.drop_column("ai_call_logs", "completed_at")
    op.drop_column("ai_call_logs", "started_at")
    op.drop_column("ai_call_logs", "failure_detail")
    op.drop_column("ai_call_logs", "status")
    op.drop_column("ai_call_logs", "provider_name")
    op.drop_column("evaluation_tasks", "input_file_path")
