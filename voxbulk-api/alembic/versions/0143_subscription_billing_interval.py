"""Add billing_interval to subscriptions and billing redirect flows."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0143_subscription_billing_interval"
down_revision = "0141_disabled_wa_template_survey_type"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_column("subscriptions", "billing_interval"):
        op.add_column(
            "subscriptions",
            sa.Column("billing_interval", sa.String(length=10), nullable=False, server_default="monthly"),
        )
    if not _has_column("billing_redirect_flows", "billing_interval"):
        op.add_column(
            "billing_redirect_flows",
            sa.Column("billing_interval", sa.String(length=10), nullable=True),
        )


def downgrade() -> None:
    if _has_column("billing_redirect_flows", "billing_interval"):
        op.drop_column("billing_redirect_flows", "billing_interval")
    if _has_column("subscriptions", "billing_interval"):
        op.drop_column("subscriptions", "billing_interval")
