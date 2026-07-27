"""Store outbound email snapshot on campaign recipients for reply thread view.

Revision ID: 0204_ai_team_outbound_snapshot
Revises: 0203_ai_team_inbound_messages
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0204_ai_team_outbound_snapshot"
down_revision = "0203_ai_team_inbound_messages"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    table = "ai_team_campaign_recipients"
    if not _has_column(table, "last_outbound_subject"):
        op.add_column(table, sa.Column("last_outbound_subject", sa.String(length=500), nullable=True))
    if not _has_column(table, "last_outbound_text"):
        op.add_column(table, sa.Column("last_outbound_text", sa.Text(), nullable=True))
    if not _has_column(table, "last_outbound_html"):
        op.add_column(table, sa.Column("last_outbound_html", sa.Text(), nullable=True))


def downgrade() -> None:
    table = "ai_team_campaign_recipients"
    for col in ("last_outbound_html", "last_outbound_text", "last_outbound_subject"):
        if _has_column(table, col):
            op.drop_column(table, col)
