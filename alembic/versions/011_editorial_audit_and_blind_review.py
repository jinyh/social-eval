"""add editorial audit presentation and blind expert review fields

Revision ID: 011
Revises: 010
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_tasks",
        sa.Column(
            "model_set_version",
            sa.String(length=100),
            nullable=False,
            server_default="six-dimension-v1",
        ),
    )
    op.add_column(
        "evaluation_tasks",
        sa.Column(
            "run_role",
            sa.String(length=30),
            nullable=False,
            server_default="production",
        ),
    )
    op.add_column(
        "evaluation_tasks",
        sa.Column("comparison_group_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("formal_check_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("formal_check_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("formal_check_override_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "editorial_decisions",
        sa.Column(
            "decision_stage",
            sa.String(length=30),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "expert_reviews",
        sa.Column("blind_submitted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "expert_reviews",
        sa.Column("ai_revealed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "review_comments",
        sa.Column("statement_decisions", sa.JSON(), nullable=True),
    )
    op.add_column(
        "review_comments",
        sa.Column("comparison_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("review_comments", "comparison_reason")
    op.drop_column("review_comments", "statement_decisions")
    op.drop_column("expert_reviews", "ai_revealed_at")
    op.drop_column("expert_reviews", "blind_submitted_at")
    op.drop_column("editorial_decisions", "decision_stage")
    op.drop_column("editorial_submissions", "formal_check_override_reason")
    op.drop_column("editorial_submissions", "formal_check_result")
    op.drop_column("editorial_submissions", "formal_check_status")
    op.drop_column("evaluation_tasks", "comparison_group_id")
    op.drop_column("evaluation_tasks", "run_role")
    op.drop_column("evaluation_tasks", "model_set_version")
