"""add signal_check_result and aggregate_result to papers

v0.14 规程第 3 阶段信号校验结果与聚合契约输出持久化（v2.45 D 路径工程对齐）。

Revision ID: 008
Revises: 007
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # v2.45 信号校验与聚合结果：与 precheck_result 并列存放在 papers 表
    op.add_column(
        "papers",
        sa.Column("signal_check_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("aggregate_result", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("papers", "aggregate_result")
    op.drop_column("papers", "signal_check_result")
