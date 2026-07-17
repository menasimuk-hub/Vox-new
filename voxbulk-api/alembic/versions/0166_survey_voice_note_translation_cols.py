"""0166 — durable translation fields on survey_voice_note_jobs.

Revision ID: 0166_survey_voice_note_translation
Revises: 0165_user_token_version
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0166_survey_voice_note_translation"
down_revision = "0165_user_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("survey_voice_note_jobs", sa.Column("original_text", sa.Text(), nullable=True))
    op.add_column("survey_voice_note_jobs", sa.Column("translated_text", sa.Text(), nullable=True))
    op.add_column("survey_voice_note_jobs", sa.Column("translation_status", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_survey_voice_note_jobs_translation_status",
        "survey_voice_note_jobs",
        ["translation_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_survey_voice_note_jobs_translation_status", table_name="survey_voice_note_jobs")
    op.drop_column("survey_voice_note_jobs", "translation_status")
    op.drop_column("survey_voice_note_jobs", "translated_text")
    op.drop_column("survey_voice_note_jobs", "original_text")
