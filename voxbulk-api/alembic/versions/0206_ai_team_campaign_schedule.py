"""Add scheduled_at to AI Team campaigns for delayed send.

Revision ID: 0206_ai_team_campaign_schedule
Revises: 0205_ai_team_send_interval
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0206_ai_team_campaign_schedule"
down_revision = "0205_ai_team_send_interval"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    table = "ai_team_campaigns"
    if not _has_column(table, "scheduled_at"):
        op.add_column(table, sa.Column("scheduled_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    table = "ai_team_campaigns"
    if _has_column(table, "scheduled_at"):
        op.drop_column(table, "scheduled_at")
