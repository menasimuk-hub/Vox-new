"""Feedback pricing v2 — web survey quotas, yearly prices, Task 7 tiers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0135_feedback_pricing_v2"
down_revision = "0134_survey_type_customer_hidden"
branch_labels = None
depends_on = None

# Task 7 list prices (minor units, ex-VAT): tier -> currency -> monthly
_TIER_MONTHLY = {
    "starter": {"GBP": 2500, "EUR": 2900, "USD": 3500, "CAD": 4900, "AUD": 4900},
    "pro": {"GBP": 6500, "EUR": 7500, "USD": 8900, "CAD": 12500, "AUD": 12900},
    "business": {"GBP": 17500, "EUR": 19900, "USD": 22900, "CAD": 32900, "AUD": 33500},
}

_TIER_LIMITS = {
    "starter": {"max_locations": 1, "wa_units": 150, "web_units": 200},
    "pro": {"max_locations": 3, "wa_units": 450, "web_units": 600},
    "business": {"max_locations": 10, "wa_units": 1500, "web_units": -1},
}


def _has_column(inspector, table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in inspector.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Idempotent column adds — a prior partial run on MySQL auto-commits DDL,
    # so guard against "Duplicate column" when the migration is retried.
    if not _has_column(inspector, "feedback_packages", "web_units_included"):
        op.add_column(
            "feedback_packages",
            sa.Column("web_units_included", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(inspector, "feedback_usage_periods", "web_units_included"):
        op.add_column(
            "feedback_usage_periods",
            sa.Column("web_units_included", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(inspector, "feedback_usage_periods", "web_units_used"):
        op.add_column(
            "feedback_usage_periods",
            sa.Column("web_units_used", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(inspector, "plan_prices", "yearly_price_minor"):
        op.add_column("plan_prices", sa.Column("yearly_price_minor", sa.Integer(), nullable=True))
    for tier, limits in _TIER_LIMITS.items():
        conn.execute(
            sa.text(
                """
                UPDATE feedback_packages
                SET max_locations = :max_locations,
                    wa_units_included = :wa_units,
                    web_units_included = :web_units
                WHERE plan_id IN (
                    SELECT id FROM plans
                    WHERE service_kind = 'customer_feedback'
                      AND code LIKE :code_pattern
                )
                """
            ),
            {
                "max_locations": limits["max_locations"],
                "wa_units": limits["wa_units"],
                "web_units": limits["web_units"],
                "code_pattern": f"cf_{tier}_%",
            },
        )
        for currency, monthly in _TIER_MONTHLY[tier].items():
            conn.execute(
                sa.text(
                    """
                    UPDATE plan_prices
                    SET monthly_price_minor = :monthly,
                        yearly_price_minor = :yearly
                    WHERE currency = :currency
                      AND plan_id IN (
                        SELECT id FROM plans
                        WHERE service_kind = 'customer_feedback'
                          AND code LIKE :code_pattern
                      )
                    """
                ),
                {
                    "monthly": monthly,
                    "yearly": monthly * 10,
                    "currency": currency,
                    "code_pattern": f"cf_{tier}_%",
                },
            )
        conn.execute(
            sa.text(
                """
                UPDATE plans
                SET name = CASE
                    WHEN code LIKE 'cf_starter_%' THEN 'Starter'
                    WHEN code LIKE 'cf_pro_%' THEN 'Growth'
                    WHEN code LIKE 'cf_business_%' THEN 'Business'
                    ELSE name
                END
                WHERE service_kind = 'customer_feedback'
                  AND code LIKE :code_pattern
                """
            ),
            {"code_pattern": f"cf_{tier}_%"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _has_column(inspector, "plan_prices", "yearly_price_minor"):
        op.drop_column("plan_prices", "yearly_price_minor")
    if _has_column(inspector, "feedback_usage_periods", "web_units_used"):
        op.drop_column("feedback_usage_periods", "web_units_used")
    if _has_column(inspector, "feedback_usage_periods", "web_units_included"):
        op.drop_column("feedback_usage_periods", "web_units_included")
    if _has_column(inspector, "feedback_packages", "web_units_included"):
        op.drop_column("feedback_packages", "web_units_included")
