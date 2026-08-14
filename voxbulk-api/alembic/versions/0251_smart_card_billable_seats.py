"""0251 — Smart Card billable seats + free window for newly added seats.

Revision ID: 0251_smart_card_billable_seats
Revises: 0250_agent_supports_ai_demo
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0251_smart_card_billable_seats"
down_revision = "0250_agent_supports_ai_demo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("billable_seat_quantity", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("added_seats_free_until", sa.DateTime(), nullable=True))
    # Backfill: entitled seats that are already past trial are fully billable.
    op.execute(
        """
        UPDATE subscriptions
        SET billable_seat_quantity = seat_quantity
        WHERE service_code = 'smart_card'
          AND seat_quantity IS NOT NULL
          AND seat_quantity > 0
          AND LOWER(COALESCE(status, '')) NOT IN ('trial', 'trialing')
        """
    )
    op.execute(
        """
        UPDATE subscriptions
        SET billable_seat_quantity = 0
        WHERE service_code = 'smart_card'
          AND LOWER(COALESCE(status, '')) IN ('trial', 'trialing')
        """
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "added_seats_free_until")
    op.drop_column("subscriptions", "billable_seat_quantity")
