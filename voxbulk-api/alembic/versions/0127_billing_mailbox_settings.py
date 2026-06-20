"""Billing mailbox settings for billing@voxbulk.com IMAP + outbound From routing.

Revision ID: 0127_billing_mailbox_settings
Revises: 0126_crm_survey_automation_events
"""

from alembic import op
import sqlalchemy as sa

revision = "0127_billing_mailbox_settings"
down_revision = "0126_crm_survey_automation_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_mailbox_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mailbox_email", sa.String(320), nullable=False, server_default="billing@voxbulk.com"),
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_ok", sa.Boolean(), nullable=True),
        sa.Column("last_sync_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("billing_mailbox_settings")
