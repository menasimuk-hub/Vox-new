"""Silent Expo 3-day company-email signup trial — superseded parent for unified promos.

Revision ID: 0192_unified_promo_redesign
Revises: 0191_expo_signup_company_trial
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0192_unified_promo_redesign"
down_revision = "0191_expo_signup_company_trial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promo_offers", sa.Column("benefit_kind", sa.String(length=32), nullable=True))
    op.add_column("promo_offers", sa.Column("discount_type", sa.String(length=32), nullable=True))
    op.add_column("promo_offers", sa.Column("discount_value", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("promo_offers", sa.Column("usage_amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "promo_offers",
        sa.Column("redeem_mode", sa.String(length=32), nullable=False, server_default="anyone"),
    )

    op.add_column(
        "organisations",
        sa.Column("feedback_credits_balance", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "promo_pending_discounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("promo_offer_id", sa.String(length=36), sa.ForeignKey("promo_offers.id"), nullable=False),
        sa.Column("service_kind", sa.String(length=32), nullable=False),
        sa.Column("discount_type", sa.String(length=32), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_promo_pending_discounts_org_id", "promo_pending_discounts", ["org_id"])
    op.create_index("ix_promo_pending_discounts_promo_offer_id", "promo_pending_discounts", ["promo_offer_id"])
    op.create_index("ix_promo_pending_discounts_status", "promo_pending_discounts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_promo_pending_discounts_status", table_name="promo_pending_discounts")
    op.drop_index("ix_promo_pending_discounts_promo_offer_id", table_name="promo_pending_discounts")
    op.drop_index("ix_promo_pending_discounts_org_id", table_name="promo_pending_discounts")
    op.drop_table("promo_pending_discounts")
    op.drop_column("organisations", "feedback_credits_balance")
    op.drop_column("promo_offers", "redeem_mode")
    op.drop_column("promo_offers", "usage_amount")
    op.drop_column("promo_offers", "discount_value")
    op.drop_column("promo_offers", "discount_type")
    op.drop_column("promo_offers", "benefit_kind")
