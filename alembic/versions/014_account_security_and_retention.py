"""add account security, MFA and retention controls

Revision ID: 014
Revises: 013
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "password_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_secret_encrypted", sa.String(length=500), nullable=True),
    )
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(), nullable=True))

    op.alter_column("invitations", "token", existing_type=sa.String(255), nullable=True)
    op.add_column(
        "invitations", sa.Column("token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column("invitations", sa.Column("revoked_at", sa.DateTime(), nullable=True))
    op.add_column("invitations", sa.Column("sent_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint(
        "uq_invitations_token_hash", "invitations", ["token_hash"]
    )
    # 已有邀请和发件箱可能含明文令牌；上线前统一撤销并由管理员重发。
    op.execute(
        "UPDATE invitations SET revoked_at = CURRENT_TIMESTAMP, token = NULL "
        "WHERE is_used = false"
    )
    op.execute("UPDATE invitations SET token = NULL WHERE is_used = true")
    op.execute(
        "UPDATE email_deliveries SET template_data = NULL "
        "WHERE event_type = 'invitation_created'"
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        "UPDATE api_keys SET expires_at = created_at + INTERVAL '90 days' "
        "WHERE expires_at IS NULL"
    )
    op.alter_column(
        "api_keys", "expires_at", existing_type=sa.DateTime(), nullable=False
    )

    op.add_column(
        "editorial_submissions",
        sa.Column("retention_due_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("retention_hold_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("content_deleted_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("editorial_submissions", "content_deleted_at")
    op.drop_column("editorial_submissions", "retention_hold_at")
    op.drop_column("editorial_submissions", "retention_due_at")
    op.alter_column(
        "api_keys", "expires_at", existing_type=sa.DateTime(), nullable=True
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_table("password_reset_tokens")
    op.drop_constraint("uq_invitations_token_hash", "invitations", type_="unique")
    op.drop_column("invitations", "sent_at")
    op.drop_column("invitations", "revoked_at")
    op.drop_column("invitations", "token_hash")
    op.execute("UPDATE invitations SET token = 'revoked-' || id WHERE token IS NULL")
    op.alter_column(
        "invitations", "token", existing_type=sa.String(255), nullable=False
    )
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_reset_required")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "session_version")
