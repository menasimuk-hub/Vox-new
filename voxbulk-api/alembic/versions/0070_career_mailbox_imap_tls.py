"""Add IMAP STARTTLS flag for career mailbox (mirrors SMTP encryption modes).

Revision ID: 0070_career_mailbox_imap_tls
Revises: 0069_career_mailbox_reference
"""

from alembic import op
import sqlalchemy as sa

revision = "0070_career_mailbox_imap_tls"
down_revision = "0069_career_mailbox_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "career_mailbox_settings",
        sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("career_mailbox_settings", "imap_use_tls")
