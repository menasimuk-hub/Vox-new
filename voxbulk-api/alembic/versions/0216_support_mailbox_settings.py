"""0216 — Support mailbox IMAP/SMTP for support@ → tickets.

Revision ID: 0216_support_mailbox_settings
Revises: 0215_billing_redirect_seat_quantity
"""

from alembic import op
import sqlalchemy as sa

revision = "0216_support_mailbox_settings"
down_revision = "0215_billing_redirect_seat_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_mailbox_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mailbox_email", sa.String(320), nullable=False, server_default="support@voxbulk.com"),
        sa.Column("from_name", sa.String(255), nullable=False, server_default="VOXBULK Support"),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_ok", sa.Boolean(), nullable=True),
        sa.Column("last_sync_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("support_mailbox_settings")
