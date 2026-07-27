"""Add event_name for Apify campaigns and recipients ({{event-name}} merge tag).

Revision ID: 0201_ai_team_event_name
Revises: 0200_ai_team_unsubscribe_imap
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0201_ai_team_event_name"
down_revision = "0200_ai_team_unsubscribe_imap"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if _has_table("ai_team_campaigns") and not _has_column("ai_team_campaigns", "event_name"):
        op.add_column(
            "ai_team_campaigns",
            sa.Column("event_name", sa.String(length=255), nullable=False, server_default=""),
        )
    if _has_table("ai_team_campaign_recipients") and not _has_column(
        "ai_team_campaign_recipients", "event_name"
    ):
        op.add_column(
            "ai_team_campaign_recipients",
            sa.Column("event_name", sa.String(length=255), nullable=False, server_default=""),
        )


def downgrade() -> None:
    if _has_table("ai_team_campaign_recipients") and _has_column(
        "ai_team_campaign_recipients", "event_name"
    ):
        op.drop_column("ai_team_campaign_recipients", "event_name")
    if _has_table("ai_team_campaigns") and _has_column("ai_team_campaigns", "event_name"):
        op.drop_column("ai_team_campaigns", "event_name")
