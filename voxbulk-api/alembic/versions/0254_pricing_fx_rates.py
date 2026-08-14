"""0254 — GBP FX rates for catalog pricing sync + manual override flags.

Revision ID: 0254_pricing_fx_rates
Revises: 0253_feedback_session_dashboard_opened
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0254_pricing_fx_rates"
down_revision = "0253_feedback_session_dashboard_opened"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pricing_fx_rates",
        sa.Column("quote_currency", sa.String(length=3), primary_key=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False, server_default="GBP"),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # Approx mid-market rates for 1 GBP as of 2026-08-14 (Admin can edit later).
    op.execute(
        """
        INSERT INTO pricing_fx_rates (quote_currency, base_currency, rate, source, updated_at) VALUES
        ('EUR', 'GBP', 1.17010000, 'seed_2026-08-14', UTC_TIMESTAMP()),
        ('USD', 'GBP', 1.35330000, 'seed_2026-08-14', UTC_TIMESTAMP()),
        ('CAD', 'GBP', 1.88350000, 'seed_2026-08-14', UTC_TIMESTAMP()),
        ('AUD', 'GBP', 1.91200000, 'seed_2026-08-14', UTC_TIMESTAMP())
        """
    )

    op.add_column(
        "plan_prices",
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "pricing_currency_settings",
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("pricing_currency_settings", "manual_override")
    op.drop_column("plan_prices", "manual_override")
    op.drop_table("pricing_fx_rates")
