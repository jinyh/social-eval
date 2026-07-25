"""persist the second-round review protocol version

Revision ID: 013
Revises: 012
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_tasks",
        sa.Column(
            "review_protocol_version",
            sa.String(length=100),
            nullable=False,
            server_default="six_dimension_cross_review",
        ),
    )


def downgrade() -> None:
    op.drop_column("evaluation_tasks", "review_protocol_version")
