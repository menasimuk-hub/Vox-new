"""password reset tokens

Revision ID: 0021_password_reset_tokens
Revises: 0020_smtp_email_templates
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_password_reset_tokens"
down_revision = "0020_smtp_email_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hmac", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_password_reset_token_hmac", "password_reset_tokens", ["token_hmac"], unique=True)
    op.create_index("ix_password_reset_user_id", "password_reset_tokens", ["user_id"], unique=False)
    op.create_index("ix_password_reset_user_unused", "password_reset_tokens", ["user_id", "used_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_password_reset_user_unused", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_token_hmac", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
