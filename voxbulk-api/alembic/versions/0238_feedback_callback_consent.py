"""Add nullable callback_consent on feedback_sessions.

Idempotent column add for MySQL/SQLite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0238_feedback_callback_consent"
down_revision = "0237_feedback_preview_entitlement"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    if _has_table("feedback_sessions") and not _has_column("feedback_sessions", "callback_consent"):
        op.add_column(
            "feedback_sessions",
            sa.Column("callback_consent", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("feedback_sessions", "callback_consent"):
        op.drop_column("feedback_sessions", "callback_consent")
