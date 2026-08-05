"""Track detected language, STT provider and low-confidence flag on voice note jobs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0228_voice_job_language_quality"
down_revision = "0227_smart_card_rep_photo"
branch_labels = None
depends_on = None

_COLUMNS = {
    "smart_card_voice_note_jobs": (
        ("detected_language", sa.String(length=32), True, None),
        ("stt_provider", sa.String(length=32), True, None),
        ("low_confidence", sa.Boolean(), False, sa.false()),
    ),
    "expo_voice_note_jobs": (
        ("stt_provider", sa.String(length=32), True, None),
        ("low_confidence", sa.Boolean(), False, sa.false()),
    ),
}


def _table_exists(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        if not _table_exists(table):
            continue
        for name, type_, nullable, default in columns:
            if _has_column(table, name):
                continue
            op.add_column(
                table,
                sa.Column(name, type_, nullable=nullable, server_default=default),
            )


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        for name, *_ in columns:
            if _has_column(table, name):
                op.drop_column(table, name)
