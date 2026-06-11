"""Support ticket links for billing cancellation requests."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0114_billing_request_tickets"
down_revision = "0113_subscription_cancellation_refund_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_refund_reviews",
        sa.Column("support_ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=True),
    )
    op.create_index("ix_billing_refund_reviews_support_ticket", "billing_refund_reviews", ["support_ticket_id"])
    op.add_column(
        "subscriptions",
        sa.Column("cancellation_support_ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "cancellation_support_ticket_id")
    op.drop_index("ix_billing_refund_reviews_support_ticket", table_name="billing_refund_reviews")
    op.drop_column("billing_refund_reviews", "support_ticket_id")
