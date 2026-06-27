"""Backfill feedback_usage_periods.web_units_included for unlimited Business packages."""

from __future__ import annotations

from alembic import op

revision = "0136_feedback_usage_unlimited_backfill"
down_revision = "0135_feedback_pricing_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE feedback_usage_periods p
        INNER JOIN subscriptions s ON s.id = p.subscription_id
        INNER JOIN feedback_packages fp ON fp.plan_id = s.plan_id
        SET p.web_units_included = -1,
            p.updated_at = NOW()
        WHERE fp.web_units_included = -1
          AND p.web_units_included <> -1
        """
    )


def downgrade() -> None:
    pass
