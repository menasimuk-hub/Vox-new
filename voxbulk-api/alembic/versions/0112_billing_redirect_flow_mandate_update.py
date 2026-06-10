"""Billing redirect flow mandate-update fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0112_billing_redirect_flow_mandate_update"
down_revision = "0111_payment_workflow_account_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("billing_redirect_flows", sa.Column("flow_purpose", sa.String(length=40), nullable=True))
    op.add_column("billing_redirect_flows", sa.Column("previous_mandate_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("billing_redirect_flows", "previous_mandate_id")
    op.drop_column("billing_redirect_flows", "flow_purpose")
