"""Add smart_card_representatives.question_config_json for per-QR overrides.

Idempotent for MySQL deploy retries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0241_smart_card_rep_question_config"
down_revision = "0240_feedback_session_entry_channel"
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


def upgrade() -> None:
    if not _has_table("smart_card_representatives"):
        return
    if not _has_column("smart_card_representatives", "question_config_json"):
        op.add_column(
            "smart_card_representatives",
            sa.Column("question_config_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("smart_card_representatives"):
        return
    if _has_column("smart_card_representatives", "question_config_json"):
        op.drop_column("smart_card_representatives", "question_config_json")
