"""0246 — user email notification preferences.

MySQL note: FK to users.id must match that column's type/charset/collation
(error 3780 otherwise). Idempotent for partial failed runs.

Revision ID: 0246_user_email_preferences
Revises: 0245_ai_demo_tracking
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0246_user_email_preferences"
down_revision = "0245_ai_demo_tracking"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _users_id_column() -> sa.TypeEngine:
    """Mirror users.id so MySQL accepts the FK (errno 3780)."""
    bind = op.get_bind()
    try:
        row = bind.execute(
            sa.text(
                "SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, CHARACTER_SET_NAME, COLLATION_NAME "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id' "
                "LIMIT 1"
            )
        ).first()
    except Exception:
        row = None

    if not row:
        return sa.String(36)

    data_type = (row[0] or "varchar").lower()
    length = int(row[1] or 36)
    collation = row[3]
    type_cls = sa.CHAR if data_type == "char" else sa.String
    if collation:
        return type_cls(length, collation=collation)
    return type_cls(length)


def _table_kwargs() -> dict:
    bind = op.get_bind()
    try:
        row = bind.execute(
            sa.text(
                "SELECT CHARACTER_SET_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id' "
                "LIMIT 1"
            )
        ).first()
    except Exception:
        row = None
    if not row:
        return {}
    charset, collation = row[0], row[1]
    kwargs: dict = {}
    if charset:
        kwargs["mysql_charset"] = charset
    if collation:
        kwargs["mysql_collate"] = collation
    return kwargs


def upgrade() -> None:
    if _has_table("user_email_preferences"):
        return

    op.create_table(
        "user_email_preferences",
        sa.Column("user_id", _users_id_column(), nullable=False),
        sa.Column("preferences_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        **_table_kwargs(),
    )


def downgrade() -> None:
    if _has_table("user_email_preferences"):
        op.drop_table("user_email_preferences")
