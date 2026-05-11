"""add billing plans/subscriptions

Revision ID: 0003_add_billing_plans_subscriptions
Revises: 0002_add_branch_patient_appointment_logs
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_billing_plans_subscriptions"
down_revision = "0002_add_branch_patient_appointment_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price_gbp_pence", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("uq_plans_code", "plans", ["code"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"], unique=False)
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_subscriptions_plan_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_org_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("uq_plans_code", table_name="plans")
    op.drop_table("plans")

