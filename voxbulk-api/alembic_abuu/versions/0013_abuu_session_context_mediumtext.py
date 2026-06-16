"""Widen abuu_conversation_sessions.context_json to MEDIUMTEXT."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0013_abuu_session_context_mediumtext"
down_revision = "0012_abuu_gaza_agent_snapshots"
branch_labels = None
depends_on = None


def _widen_alembic_version_column() -> None:
    """Alembic defaults to VARCHAR(32); long revision ids (e.g. this one) need more."""
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    insp = sa.inspect(bind)
    if "alembic_version" not in insp.get_table_names():
        return
    op.execute(sa.text("ALTER TABLE alembic_version MODIFY version_num VARCHAR(64) NOT NULL"))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    _widen_alembic_version_column()

    insp = sa.inspect(bind)
    cols = {c["name"]: c for c in insp.get_columns("abuu_conversation_sessions")}
    if "context_json" not in cols:
        return
    col_type = str(cols["context_json"]["type"]).upper()
    if "MEDIUMTEXT" in col_type:
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
