"""Subscription cancellation fields and billing refund review queue."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0113_subscription_cancellation_refund_review"
down_revision = "0112_billing_redirect_flow_mandate_update"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("cancellation_status", sa.String(length=30), nullable=False, server_default="none"))
    op.add_column("subscriptions", sa.Column("cancellation_type", sa.String(length=30), nullable=True))
    op.add_column("subscriptions", sa.Column("cancellation_reason", sa.String(length=2000), nullable=True))
    op.add_column("subscriptions", sa.Column("cancellation_requested_at", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("cancellation_effective_at", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("requested_refund_type", sa.String(length=40), nullable=True))
    op.add_column("subscriptions", sa.Column("cancellation_requested_by_user_id", sa.String(length=36), nullable=True))

    op.create_table(
        "billing_refund_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("subscription_id", sa.String(length=36), sa.ForeignKey("subscriptions.id"), nullable=True, index=True),
        sa.Column("source_payment_provider", sa.String(length=30), nullable=True),
        sa.Column("source_payment_reference", sa.String(length=128), nullable=True),
        sa.Column("source_invoice_id", sa.String(length=36), sa.ForeignKey("billing_invoices.id"), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("requested_refund_type", sa.String(length=40), nullable=False),
        sa.Column("calculated_unused_value_pence", sa.Integer(), nullable=True),
        sa.Column("approved_wallet_credit_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_external_refund_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("wallet_transaction_id", sa.String(length=36), sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("credit_note_id", sa.String(length=36), sa.ForeignKey("credit_notes.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_billing_refund_reviews_status", "billing_refund_reviews", ["review_status"])
    op.create_index("ux_billing_refund_reviews_idempotency", "billing_refund_reviews", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_billing_refund_reviews_idempotency", table_name="billing_refund_reviews")
    op.drop_index("ix_billing_refund_reviews_status", table_name="billing_refund_reviews")
    op.drop_table("billing_refund_reviews")
    op.drop_column("subscriptions", "cancellation_requested_by_user_id")
    op.drop_column("subscriptions", "requested_refund_type")
    op.drop_column("subscriptions", "cancellation_effective_at")
    op.drop_column("subscriptions", "cancellation_requested_at")
    op.drop_column("subscriptions", "cancellation_reason")
    op.drop_column("subscriptions", "cancellation_type")
    op.drop_column("subscriptions", "cancellation_status")
