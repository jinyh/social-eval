"""submission resubmission chain

Revision ID: 019
Revises: 018
Create Date: 2026-08-06

Adds root_submission_id / previous_submission_id / resubmission_round to
editorial_submissions to support "same paper, up to 3 resubmissions, counted
as 1" pre-review mode. Backfills existing rows with root_submission_id = id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "editorial_submissions",
        sa.Column("root_submission_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("previous_submission_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column(
            "resubmission_round",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_index(
        "ix_editorial_submissions_root_submission_id",
        "editorial_submissions",
        ["root_submission_id"],
    )
    op.create_foreign_key(
        "fk_submission_root",
        "editorial_submissions",
        "editorial_submissions",
        ["root_submission_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_submission_previous",
        "editorial_submissions",
        "editorial_submissions",
        ["previous_submission_id"],
        ["id"],
    )
    # 回填存量：每条投稿的 root 指向自身，round=1
    op.execute(
        "UPDATE editorial_submissions SET root_submission_id = id "
        "WHERE root_submission_id IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_submission_previous", "editorial_submissions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_submission_root", "editorial_submissions", type_="foreignkey"
    )
    op.drop_index(
        "ix_editorial_submissions_root_submission_id",
        table_name="editorial_submissions",
    )
    op.drop_column("editorial_submissions", "resubmission_round")
    op.drop_column("editorial_submissions", "previous_submission_id")
    op.drop_column("editorial_submissions", "root_submission_id")
