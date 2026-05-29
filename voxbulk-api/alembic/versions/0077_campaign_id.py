"""Add campaign_id to service_orders for interview tracking."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0077_campaign_id"
down_revision = "0076_interview_booking_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("service_orders")}
    if "campaign_id" not in cols:
        op.add_column("service_orders", sa.Column("campaign_id", sa.String(32), nullable=True))
        op.create_index("ix_service_orders_campaign_id", "service_orders", ["campaign_id"], unique=True)

    rows = bind.execute(
        sa.text(
            "SELECT id FROM service_orders WHERE service_code = 'interview' AND (campaign_id IS NULL OR campaign_id = '')"
        )
    ).fetchall()
    for (order_id,) in rows:
        token = f"VB-CMP-{uuid.uuid4().hex[:8].upper()}"
        bind.execute(
            sa.text("UPDATE service_orders SET campaign_id = :cid WHERE id = :id"),
            {"cid": token, "id": order_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("service_orders")}
    if "campaign_id" in cols:
        op.drop_index("ix_service_orders_campaign_id", table_name="service_orders")
        op.drop_column("service_orders", "campaign_id")
