"""Expo asset purpose + lead asset open tracking.

Revision ID: 0189_expo_asset_purpose_opened
Revises: 0188_sales_payout_invoices
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0189_expo_asset_purpose_opened"
down_revision = "0188_sales_payout_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expo_booth_assets",
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="product"),
    )
    op.add_column("expo_leads", sa.Column("assets_opened_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("expo_leads", "assets_opened_json")
    op.drop_column("expo_booth_assets", "purpose")
