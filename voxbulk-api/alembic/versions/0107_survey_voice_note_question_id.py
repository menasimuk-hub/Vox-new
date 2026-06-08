"""Add question_id and processed_at to survey voice note jobs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0107_survey_voice_note_question_id"
down_revision = "0106_wa_survey_pricing_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("survey_voice_note_jobs", sa.Column("question_id", sa.String(length=128), nullable=True))
    op.add_column("survey_voice_note_jobs", sa.Column("processed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("survey_voice_note_jobs", "processed_at")
    op.drop_column("survey_voice_note_jobs", "question_id")
