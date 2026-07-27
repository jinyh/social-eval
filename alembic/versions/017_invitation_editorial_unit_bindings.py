"""invitation carries editorial unit bindings

Revision ID: 017
Revises: 016
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invitations",
        sa.Column("unit_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "invitations",
        sa.Column(
            "membership_role",
            sa.String(length=30),
            nullable=False,
            server_default="editor",
        ),
    )


def downgrade() -> None:
    op.drop_column("invitations", "membership_role")
    op.drop_column("invitations", "unit_ids")
