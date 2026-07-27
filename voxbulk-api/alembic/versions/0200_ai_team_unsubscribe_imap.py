"""AI Team unsubscribe suppressions + IMAP inbound + recipient inbound fields.

Revision ID: 0200_ai_team_unsubscribe_imap
Revises: 0199_ai_team_campaign_click_tracking
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0200_ai_team_unsubscribe_imap"
down_revision = "0199_ai_team_campaign_click_tracking"
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
    if not _has_table("ai_team_email_suppressions"):
        op.create_table(
            "ai_team_email_suppressions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("unsubscribed_at", sa.DateTime(), nullable=False),
            sa.Column("source_recipient_id", sa.String(length=36), nullable=True),
            sa.Column("source_campaign_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ai_team_email_suppressions_email", "ai_team_email_suppressions", ["email"], unique=True)

    if _has_table("ai_team_campaign_recipients"):
        if not _has_column("ai_team_campaign_recipients", "unsubscribed_at"):
            op.add_column("ai_team_campaign_recipients", sa.Column("unsubscribed_at", sa.DateTime(), nullable=True))
        if not _has_column("ai_team_campaign_recipients", "last_inbound_subject"):
            op.add_column(
                "ai_team_campaign_recipients",
                sa.Column("last_inbound_subject", sa.String(length=500), nullable=True),
            )
        if not _has_column("ai_team_campaign_recipients", "last_inbound_body"):
            op.add_column("ai_team_campaign_recipients", sa.Column("last_inbound_body", sa.Text(), nullable=True))

    if _has_table("ai_team_settings"):
        cols = [
            ("imap_host", sa.Column("imap_host", sa.String(length=255), nullable=False, server_default="")),
            ("imap_port", sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993")),
            ("imap_use_ssl", sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true())),
            ("imap_use_tls", sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("imap_username", sa.Column("imap_username", sa.String(length=320), nullable=False, server_default="")),
            ("imap_password_enc", sa.Column("imap_password_enc", sa.Text(), nullable=True)),
            ("imap_last_sync_at", sa.Column("imap_last_sync_at", sa.DateTime(), nullable=True)),
            ("imap_last_sync_message", sa.Column("imap_last_sync_message", sa.String(length=500), nullable=True)),
        ]
        for name, col in cols:
            if not _has_column("ai_team_settings", name):
                op.add_column("ai_team_settings", col)


def downgrade() -> None:
    if _has_table("ai_team_settings"):
        for name in (
            "imap_last_sync_message",
            "imap_last_sync_at",
            "imap_password_enc",
            "imap_username",
            "imap_use_tls",
            "imap_use_ssl",
            "imap_port",
            "imap_host",
        ):
            if _has_column("ai_team_settings", name):
                op.drop_column("ai_team_settings", name)

    if _has_table("ai_team_campaign_recipients"):
        for name in ("last_inbound_body", "last_inbound_subject", "unsubscribed_at"):
            if _has_column("ai_team_campaign_recipients", name):
                op.drop_column("ai_team_campaign_recipients", name)

    if _has_table("ai_team_email_suppressions"):
        op.drop_index("ix_ai_team_email_suppressions_email", table_name="ai_team_email_suppressions")
        op.drop_table("ai_team_email_suppressions")
