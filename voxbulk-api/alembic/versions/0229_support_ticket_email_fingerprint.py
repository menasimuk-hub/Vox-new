"""Add email_fingerprint on support tickets for salesman escalation IMAP dedupe.

Revision ID: 0229_support_ticket_email_fingerprint
Revises: 0228_voice_job_language_quality
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0229_support_ticket_email_fingerprint"
down_revision = "0228_voice_job_language_quality"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("support_tickets"):
        return
    if not _has_column("support_tickets", "email_fingerprint"):
        op.add_column(
            "support_tickets",
            sa.Column("email_fingerprint", sa.String(length=120), nullable=True),
        )
    # Unique + non-unique index names vary by dialect; create if missing.
    bind = op.get_bind()
    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("support_tickets")}
    if "ix_support_tickets_email_fingerprint" not in indexes:
        op.create_index(
            "ix_support_tickets_email_fingerprint",
            "support_tickets",
            ["email_fingerprint"],
            unique=True,
        )


def downgrade() -> None:
    if not _table_exists("support_tickets"):
        return
    bind = op.get_bind()
    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("support_tickets")}
    if "ix_support_tickets_email_fingerprint" in indexes:
        op.drop_index("ix_support_tickets_email_fingerprint", table_name="support_tickets")
    if _has_column("support_tickets", "email_fingerprint"):
        op.drop_column("support_tickets", "email_fingerprint")
