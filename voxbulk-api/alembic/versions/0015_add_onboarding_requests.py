"""add onboarding_requests

Revision ID: 0015_add_onboarding_requests
Revises: 0014_add_membership_role
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_add_onboarding_requests"
down_revision = "0014_add_membership_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("payment_method", sa.String(length=32), nullable=False, server_default="bank_transfer"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_onboarding_requests_org_id", "onboarding_requests", ["org_id"], unique=False)
    op.create_index("ix_onboarding_requests_user_id", "onboarding_requests", ["user_id"], unique=False)
    op.create_index("ix_onboarding_requests_status", "onboarding_requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_onboarding_requests_status", table_name="onboarding_requests")
    op.drop_index("ix_onboarding_requests_user_id", table_name="onboarding_requests")
    op.drop_index("ix_onboarding_requests_org_id", table_name="onboarding_requests")
    op.drop_table("onboarding_requests")

