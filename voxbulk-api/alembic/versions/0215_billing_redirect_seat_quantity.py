"""Add seat_quantity to billing_redirect_flows for Smart Card GC checkout.

Revision ID: 0215_billing_redirect_seat_quantity
Revises: 0214_smart_card_mailbox_imap
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0215_billing_redirect_seat_quantity"
down_revision = "0214_smart_card_mailbox_imap"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("billing_redirect_flows", "seat_quantity"):
        op.add_column(
            "billing_redirect_flows",
            sa.Column("seat_quantity", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("billing_redirect_flows", "seat_quantity"):
        op.drop_column("billing_redirect_flows", "seat_quantity")
