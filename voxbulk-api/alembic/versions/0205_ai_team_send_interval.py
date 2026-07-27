"""Add send_interval_seconds for Apify campaign queue pacing.

Revision ID: 0205_ai_team_send_interval
Revises: 0204_ai_team_outbound_snapshot
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0205_ai_team_send_interval"
down_revision = "0204_ai_team_outbound_snapshot"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    table = "ai_team_settings"
    if not _has_column(table, "send_interval_seconds"):
        op.add_column(
            table,
            sa.Column("send_interval_seconds", sa.Integer(), nullable=False, server_default="20"),
        )


def downgrade() -> None:
    table = "ai_team_settings"
    if _has_column(table, "send_interval_seconds"):
        op.drop_column(table, "send_interval_seconds")
