"""Voxbox unified inbox tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0221_voxbox_inbox"
down_revision = "0220_merge_support_disk_sender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voxbox_admin_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "voxbox_mail_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("imap_host", sa.String(length=255), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False),
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("smtp_use_ssl", sa.Boolean(), nullable=False),
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("password_enc", sa.Text(), nullable=True),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voxbox_mail_accounts_email", "voxbox_mail_accounts", ["email"])
    op.create_index("ix_voxbox_mail_accounts_sort_order", "voxbox_mail_accounts", ["sort_order"])

    op.create_table(
        "voxbox_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("internet_message_id", sa.String(length=500), nullable=False),
        sa.Column("imap_uid", sa.String(length=64), nullable=False),
        sa.Column("folder", sa.String(length=32), nullable=False),
        sa.Column("from_name", sa.String(length=255), nullable=False),
        sa.Column("from_email", sa.String(length=320), nullable=False),
        sa.Column("to_addrs", sa.String(length=1000), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("preview", sa.String(length=500), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("unread", sa.Boolean(), nullable=False),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.Column("starred", sa.Boolean(), nullable=False),
        sa.Column("has_attachment", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["voxbox_mail_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voxbox_messages_account_id", "voxbox_messages", ["account_id"])
    op.create_index("ix_voxbox_messages_internet_message_id", "voxbox_messages", ["internet_message_id"])
    op.create_index("ix_voxbox_messages_folder", "voxbox_messages", ["folder"])
    op.create_index("ix_voxbox_messages_from_email", "voxbox_messages", ["from_email"])
    op.create_index("ix_voxbox_messages_date", "voxbox_messages", ["date"])


def downgrade() -> None:
    op.drop_table("voxbox_messages")
    op.drop_index("ix_voxbox_mail_accounts_sort_order", table_name="voxbox_mail_accounts")
    op.drop_index("ix_voxbox_mail_accounts_email", table_name="voxbox_mail_accounts")
    op.drop_table("voxbox_mail_accounts")
    op.drop_table("voxbox_admin_users")
