"""Merge Alembic heads: career mailbox IMAP TLS + org scheduling config.

Revision ID: 0071_merge_scheduling_career_heads
Revises: 0070_career_mailbox_imap_tls, 0070_org_scheduling_config
"""

revision = "0071_merge_scheduling_career_heads"
down_revision = ("0070_career_mailbox_imap_tls", "0070_org_scheduling_config")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
