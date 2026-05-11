"""subscription payment mode

Revision ID: 0029_subscription_payment_mode
Revises: 0028_notifications
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029_subscription_payment_mode"
down_revision = "0028_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("payment_provider", sa.String(length=50), nullable=False, server_default="manual_cash"))
    op.add_column("subscriptions", sa.Column("payment_mode", sa.String(length=30), nullable=False, server_default="test"))
    op.add_column("subscriptions", sa.Column("external_customer_id", sa.String(length=128), nullable=True))
    op.add_column("subscriptions", sa.Column("external_subscription_id", sa.String(length=128), nullable=True))
    op.add_column("subscriptions", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_subscriptions_external_subscription_id", "subscriptions", ["external_subscription_id"])

    op.execute("UPDATE subscriptions SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_subscriptions_external_subscription_id", table_name="subscriptions")
    op.drop_column("subscriptions", "updated_at")
    op.drop_column("subscriptions", "external_subscription_id")
    op.drop_column("subscriptions", "external_customer_id")
    op.drop_column("subscriptions", "payment_mode")
    op.drop_column("subscriptions", "payment_provider")
