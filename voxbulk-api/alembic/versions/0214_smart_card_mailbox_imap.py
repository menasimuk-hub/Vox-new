"""0214 — Smart Card mailbox IMAP/SMTP columns + industries table.

Revision ID: 0214_smart_card_mailbox_imap
Revises: 0213_smart_card_qr_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0214_smart_card_mailbox_imap"
down_revision = "0213_smart_card_qr_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("smart_card_mailbox_settings", sa.Column("smtp_host", sa.String(length=255), nullable=True))
    op.add_column("smart_card_mailbox_settings", sa.Column("smtp_port", sa.Integer(), nullable=True))
    op.add_column("smart_card_mailbox_settings", sa.Column("imap_host", sa.String(length=255), nullable=True))
    op.add_column(
        "smart_card_mailbox_settings",
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
    )
    op.add_column(
        "smart_card_mailbox_settings",
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "smart_card_mailbox_settings",
        sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("smart_card_mailbox_settings", sa.Column("imap_username", sa.String(length=255), nullable=True))
    op.add_column("smart_card_mailbox_settings", sa.Column("imap_password_encrypted", sa.Text(), nullable=True))
    op.add_column("smart_card_mailbox_settings", sa.Column("imap_last_sync_at", sa.DateTime(), nullable=True))
    op.add_column(
        "smart_card_mailbox_settings",
        sa.Column("imap_last_sync_message", sa.String(length=512), nullable=True),
    )

    op.create_table(
        "smart_card_industries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("addon_question", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "smart_card_voice_note_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["smart_card_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_voice_note_jobs_org_id", "smart_card_voice_note_jobs", ["org_id"])
    op.create_index("ix_smart_card_voice_note_jobs_session_id", "smart_card_voice_note_jobs", ["session_id"])
    op.create_index("ix_smart_card_voice_note_jobs_status", "smart_card_voice_note_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_smart_card_voice_note_jobs_status", table_name="smart_card_voice_note_jobs")
    op.drop_index("ix_smart_card_voice_note_jobs_session_id", table_name="smart_card_voice_note_jobs")
    op.drop_index("ix_smart_card_voice_note_jobs_org_id", table_name="smart_card_voice_note_jobs")
    op.drop_table("smart_card_voice_note_jobs")
    op.drop_table("smart_card_industries")
    op.drop_column("smart_card_mailbox_settings", "imap_last_sync_message")
    op.drop_column("smart_card_mailbox_settings", "imap_last_sync_at")
    op.drop_column("smart_card_mailbox_settings", "imap_password_encrypted")
    op.drop_column("smart_card_mailbox_settings", "imap_username")
    op.drop_column("smart_card_mailbox_settings", "imap_use_tls")
    op.drop_column("smart_card_mailbox_settings", "imap_use_ssl")
    op.drop_column("smart_card_mailbox_settings", "imap_port")
    op.drop_column("smart_card_mailbox_settings", "imap_host")
    op.drop_column("smart_card_mailbox_settings", "smtp_port")
    op.drop_column("smart_card_mailbox_settings", "smtp_host")
