"""Billing finance foundation: subscription visibility fields and payment event metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0117_billing_finance_foundation"
down_revision = "0116_platform_default_allowed_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("subscriptions", sa.Column("next_billing_date", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("amount_next_payment_minor", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_currency", sa.String(length=3), nullable=True))
    op.add_column("subscriptions", sa.Column("tax_rate_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("subscriptions", sa.Column("tax_country_code", sa.String(length=2), nullable=True))

    op.add_column("payment_events", sa.Column("event_kind", sa.String(length=40), nullable=True))
    op.add_column("payment_events", sa.Column("source", sa.String(length=40), nullable=True))
    op.add_column("payment_events", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("payment_events", sa.Column("actor_user_id", sa.String(length=36), nullable=True))
    op.add_column("payment_events", sa.Column("subscription_id", sa.String(length=36), nullable=True))

    op.create_index("ix_payment_events_event_kind", "payment_events", ["event_kind"])
    op.create_index("ix_payment_events_org_created", "payment_events", ["org_id", "created_at"])

    # Backfill cancel_at_period_end from existing scheduled period-end cancellations.
    op.execute(
        sa.text(
            "UPDATE subscriptions SET cancel_at_period_end = 1 "
            "WHERE cancellation_status = 'scheduled' AND cancellation_type = 'period_end'"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_org_created", table_name="payment_events")
    op.drop_index("ix_payment_events_event_kind", table_name="payment_events")
    op.drop_column("payment_events", "subscription_id")
    op.drop_column("payment_events", "actor_user_id")
    op.drop_column("payment_events", "metadata_json")
    op.drop_column("payment_events", "source")
    op.drop_column("payment_events", "event_kind")
    op.drop_column("subscriptions", "tax_country_code")
    op.drop_column("subscriptions", "tax_rate_percent")
    op.drop_column("subscriptions", "billing_currency")
    op.drop_column("subscriptions", "amount_next_payment_minor")
    op.drop_column("subscriptions", "next_billing_date")
    op.drop_column("subscriptions", "cancel_at_period_end")
