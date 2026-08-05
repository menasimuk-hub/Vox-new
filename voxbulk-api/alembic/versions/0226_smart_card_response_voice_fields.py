"""Smart Card response bilingual + voice job link for lead results parity with Expo."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0226_smart_card_response_voice_fields"
down_revision = "0225_catalogue_library_persist"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    table = "smart_card_responses"
    if not _has_column(table, "original_text"):
        op.add_column(table, sa.Column("original_text", sa.Text(), nullable=True))
    if not _has_column(table, "answer_text_en"):
        op.add_column(table, sa.Column("answer_text_en", sa.Text(), nullable=True))
    if not _has_column(table, "answer_source"):
        op.add_column(table, sa.Column("answer_source", sa.String(length=16), nullable=True))
    if not _has_column(table, "voice_job_id"):
        op.add_column(table, sa.Column("voice_job_id", sa.String(length=36), nullable=True))
        op.create_index("ix_smart_card_responses_voice_job_id", table, ["voice_job_id"])


def downgrade() -> None:
    table = "smart_card_responses"
    if _has_column(table, "voice_job_id"):
        op.drop_index("ix_smart_card_responses_voice_job_id", table_name=table)
        op.drop_column(table, "voice_job_id")
    if _has_column(table, "answer_source"):
        op.drop_column(table, "answer_source")
    if _has_column(table, "answer_text_en"):
        op.drop_column(table, "answer_text_en")
    if _has_column(table, "original_text"):
        op.drop_column(table, "original_text")
