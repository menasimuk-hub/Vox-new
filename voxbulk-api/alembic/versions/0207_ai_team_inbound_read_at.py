"""Add read_at to AI Team IMAP inbox messages (unread badge).

Revision ID: 0207_ai_team_inbound_read_at
Revises: 0206_ai_team_campaign_schedule
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0207_ai_team_inbound_read_at"
down_revision = "0206_ai_team_campaign_schedule"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = sa.inspect(bind).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    if not _has_column("ai_team_inbound_messages", "read_at"):
        op.add_column("ai_team_inbound_messages", sa.Column("read_at", sa.DateTime(), nullable=True))
        op.create_index("ix_ai_team_inbound_messages_read_at", "ai_team_inbound_messages", ["read_at"])


def downgrade() -> None:
    if _has_column("ai_team_inbound_messages", "read_at"):
        op.drop_index("ix_ai_team_inbound_messages_read_at", table_name="ai_team_inbound_messages")
        op.drop_column("ai_team_inbound_messages", "read_at")
