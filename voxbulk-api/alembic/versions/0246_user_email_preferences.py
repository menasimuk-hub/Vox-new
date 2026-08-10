"""0246 — user email notification preferences.

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


def upgrade() -> None:
    if _has_table("user_email_preferences"):
        return
    op.create_table(
        "user_email_preferences",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("preferences_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    if _has_table("user_email_preferences"):
        op.drop_table("user_email_preferences")
