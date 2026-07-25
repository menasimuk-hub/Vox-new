"""Expo booth payment status for pay-before-go-live.

Revision ID: 0186_expo_booth_payment_status
Revises: 0185_expo_booth_preview_tests
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0186_expo_booth_payment_status"
down_revision = "0185_expo_booth_preview_tests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expo_booths",
        sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="unpaid"),
    )
    op.add_column("expo_booths", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.add_column("expo_booths", sa.Column("payment_provider", sa.String(length=32), nullable=True))
    op.add_column("expo_booths", sa.Column("payment_intent_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("expo_booths", "payment_intent_id")
    op.drop_column("expo_booths", "payment_provider")
    op.drop_column("expo_booths", "paid_at")
    op.drop_column("expo_booths", "payment_status")
