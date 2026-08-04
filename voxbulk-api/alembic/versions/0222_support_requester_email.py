"""Add support ticket requester_email/name for web/IMAP contacts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0222_support_requester_email"
down_revision = "0221_voxbox_inbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_tickets", sa.Column("requester_email", sa.String(length=320), nullable=True))
    op.add_column("support_tickets", sa.Column("requester_name", sa.String(length=180), nullable=True))
    op.create_index("ix_support_tickets_requester_email", "support_tickets", ["requester_email"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_requester_email", table_name="support_tickets")
    op.drop_column("support_tickets", "requester_name")
    op.drop_column("support_tickets", "requester_email")
