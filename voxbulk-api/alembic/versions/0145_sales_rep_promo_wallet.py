"""Sales rep promo offers and restricted promo wallet balance."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0145_sales_rep_promo_wallet"
down_revision = "0144_sales_customer_funnel_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promo_offers", sa.Column("sales_rep_id", sa.String(length=36), nullable=True))
    op.add_column(
        "promo_offers",
        sa.Column("wallet_credit_pence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_promo_offers_sales_rep_id", "promo_offers", ["sales_rep_id"], unique=False)
    op.add_column(
        "organisations",
        sa.Column("promo_wallet_balance_pence", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("organisations", "promo_wallet_balance_pence")
    op.drop_index("ix_promo_offers_sales_rep_id", table_name="promo_offers")
    op.drop_column("promo_offers", "wallet_credit_pence")
    op.drop_column("promo_offers", "sales_rep_id")
