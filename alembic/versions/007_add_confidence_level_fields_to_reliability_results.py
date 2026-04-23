"""add confidence level fields to reliability_results

Revision ID: 007
Revises: 006
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加 v2.6 新增字段：分级置信度
    op.add_column("reliability_results", sa.Column("confidence_level", sa.String(20), nullable=False, server_default="high"))
    op.add_column("reliability_results", sa.Column("requires_evidence_supplement", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("reliability_results", sa.Column("divergence_description", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    # 回滚时删除这三个字段
    op.drop_column("reliability_results", "divergence_description")
    op.drop_column("reliability_results", "requires_evidence_supplement")
    op.drop_column("reliability_results", "confidence_level")
