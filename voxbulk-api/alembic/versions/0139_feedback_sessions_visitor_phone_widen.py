"""Widen feedback_sessions.visitor_phone for web:uuid identifiers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0139_feedback_sessions_visitor_phone_widen"
down_revision = "0138_merge_feedback_heads"
branch_labels = None
depends_on = None


def _column_length(inspector, table: str, column: str) -> int | None:
    try:
        for col in inspector.get_columns(table):
            if col["name"] == column:
                return col.get("type").length if hasattr(col.get("type"), "length") else None
    except Exception:
        return None
    return None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    length = _column_length(inspector, "feedback_sessions", "visitor_phone")
    if length is not None and length >= 64:
        return
    op.alter_column(
        "feedback_sessions",
        "visitor_phone",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "feedback_sessions",
        "visitor_phone",
        existing_type=sa.String(64),
        type_=sa.String(32),
        existing_nullable=False,
    )
