"""add users.is_superuser

Revision ID: 0004_add_user_is_superuser
Revises: 0003_add_billing_plans_subscriptions
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_add_user_is_superuser"
down_revision = "0003_add_billing_plans_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.alter_column("users", "is_superuser", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_superuser")

