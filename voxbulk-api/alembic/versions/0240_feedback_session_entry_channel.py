"""Add feedback_sessions.entry_channel (web | whatsapp).

Idempotent for MySQL deploy retries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0240_feedback_session_entry_channel"
down_revision = "0239_feedback_consent_events"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(col["name"] == column for col in sa.inspect(bind).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    if not _has_table("feedback_sessions"):
        return
    if not _has_column("feedback_sessions", "entry_channel"):
        op.add_column(
            "feedback_sessions",
            sa.Column("entry_channel", sa.String(length=16), nullable=True),
        )
    # Backfill from visitor_phone convention used before this column existed.
    op.execute(
        sa.text(
            "UPDATE feedback_sessions SET entry_channel = 'web' "
            "WHERE entry_channel IS NULL AND visitor_phone LIKE 'web:%'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE feedback_sessions SET entry_channel = 'whatsapp' "
            "WHERE entry_channel IS NULL"
        )
    )
    if not _has_index("feedback_sessions", "ix_feedback_sessions_entry_channel"):
        op.create_index(
            "ix_feedback_sessions_entry_channel",
            "feedback_sessions",
            ["entry_channel"],
        )


def downgrade() -> None:
    if not _has_table("feedback_sessions"):
        return
    if _has_index("feedback_sessions", "ix_feedback_sessions_entry_channel"):
        op.drop_index("ix_feedback_sessions_entry_channel", table_name="feedback_sessions")
    if _has_column("feedback_sessions", "entry_channel"):
        op.drop_column("feedback_sessions", "entry_channel")
