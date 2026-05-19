"""billing redirect flows

Revision ID: 0030_billing_redirect_flows
Revises: 0029_subscription_payment_mode
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030_billing_redirect_flows"
down_revision = "0029_subscription_payment_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_redirect_flows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("redirect_flow_id", sa.String(length=128), nullable=False),
        sa.Column("session_token", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("authorization_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_billing_redirect_flows_org_id", "billing_redirect_flows", ["org_id"])
    op.create_index("ix_billing_redirect_flows_user_id", "billing_redirect_flows", ["user_id"])
    op.create_index("ix_billing_redirect_flows_plan_id", "billing_redirect_flows", ["plan_id"])
    op.create_index("ix_billing_redirect_flows_redirect_flow_id", "billing_redirect_flows", ["redirect_flow_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_billing_redirect_flows_redirect_flow_id", table_name="billing_redirect_flows")
    op.drop_index("ix_billing_redirect_flows_plan_id", table_name="billing_redirect_flows")
    op.drop_index("ix_billing_redirect_flows_user_id", table_name="billing_redirect_flows")
    op.drop_index("ix_billing_redirect_flows_org_id", table_name="billing_redirect_flows")
    op.drop_table("billing_redirect_flows")
