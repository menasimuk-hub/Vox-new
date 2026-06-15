"""Order line unavailable + substitution + driver customer notified."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_abuu_order_substitution"
down_revision = "0010_abuu_restaurant_offers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "abuu_order_items",
        sa.Column("unavailable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("abuu_order_items", sa.Column("unavailable_at", sa.DateTime(), nullable=True))
    op.add_column("abuu_order_items", sa.Column("substitution_status", sa.String(length=32), nullable=True))
    op.add_column(
        "abuu_orders",
        sa.Column("substitution_pending", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("abuu_delivery_assignments", sa.Column("customer_notified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("abuu_delivery_assignments", "customer_notified_at")
    op.drop_column("abuu_orders", "substitution_pending")
    op.drop_column("abuu_order_items", "substitution_status")
    op.drop_column("abuu_order_items", "unavailable_at")
    op.drop_column("abuu_order_items", "unavailable")
