"""Backfill campaign_id for survey service orders."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0105_survey_campaign_ids"
down_revision = "0104_survey_voice_note_jobs"
branch_labels = None
depends_on = None

CAMPAIGN_PREFIX = "VB-CMP-"


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id FROM service_orders "
            "WHERE service_code = 'survey' AND (campaign_id IS NULL OR campaign_id = '')"
        )
    ).fetchall()
    for (order_id,) in rows:
        for _ in range(8):
            candidate = f"{CAMPAIGN_PREFIX}{uuid.uuid4().hex[:8].upper()}"
            clash = conn.execute(
                sa.text("SELECT id FROM service_orders WHERE campaign_id = :cid LIMIT 1"),
                {"cid": candidate},
            ).fetchone()
            if clash:
                continue
            conn.execute(
                sa.text("UPDATE service_orders SET campaign_id = :cid WHERE id = :id"),
                {"cid": candidate, "id": order_id},
            )
            break


def downgrade() -> None:
    pass
