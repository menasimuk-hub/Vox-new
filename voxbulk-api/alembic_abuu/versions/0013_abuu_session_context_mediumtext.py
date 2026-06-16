"""Widen abuu_conversation_sessions.context_json to MEDIUMTEXT."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0013_abuu_session_context_mediumtext"
down_revision = "0012_abuu_gaza_agent_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "abuu_conversation_sessions",
        "context_json",
        existing_type=sa.Text(),
        type_=mysql.MEDIUMTEXT(),
        existing_nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "abuu_conversation_sessions",
        "context_json",
        existing_type=mysql.MEDIUMTEXT(),
        type_=sa.Text(),
        existing_nullable=True,
    )
