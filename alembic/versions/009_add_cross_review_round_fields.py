"""add cross-review task and round audit fields

Revision ID: 009
Revises: 008
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_tasks",
        sa.Column("cross_review_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "evaluation_tasks",
        sa.Column("final_round", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "dimension_scores",
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("call_type", sa.String(length=50), nullable=False, server_default="dimension_score"),
    )
    op.add_column(
        "reliability_results",
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("reliability_results", "round_number")
    op.drop_column("ai_call_logs", "call_type")
    op.drop_column("ai_call_logs", "round_number")
    op.drop_column("dimension_scores", "round_number")
    op.drop_column("evaluation_tasks", "final_round")
    op.drop_column("evaluation_tasks", "cross_review_enabled")
