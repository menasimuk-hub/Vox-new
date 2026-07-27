"""Store all IMAP inbox messages for Apify Tracking (matched or unmatched).

Revision ID: 0203_ai_team_inbound_messages
Revises: 0202_feedback_wa_template_profile_status
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0203_ai_team_inbound_messages"
down_revision = "0202_feedback_wa_template_profile_status"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("ai_team_inbound_messages"):
        op.create_table(
            "ai_team_inbound_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("internet_message_id", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
            sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("recipient_id", sa.String(length=36), nullable=True),
            sa.Column("campaign_id", sa.String(length=36), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ai_team_inbound_messages_internet_message_id", "ai_team_inbound_messages", ["internet_message_id"])
        op.create_index("ix_ai_team_inbound_messages_from_email", "ai_team_inbound_messages", ["from_email"])
        op.create_index("ix_ai_team_inbound_messages_recipient_id", "ai_team_inbound_messages", ["recipient_id"])
        op.create_index("ix_ai_team_inbound_messages_campaign_id", "ai_team_inbound_messages", ["campaign_id"])
        op.create_index("ix_ai_team_inbound_messages_received_at", "ai_team_inbound_messages", ["received_at"])


def downgrade() -> None:
    if _has_table("ai_team_inbound_messages"):
        op.drop_table("ai_team_inbound_messages")
