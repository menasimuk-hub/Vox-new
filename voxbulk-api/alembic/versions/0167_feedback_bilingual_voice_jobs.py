"""0167 — CF bilingual status columns + feedback_voice_note_jobs.

Revision ID: 0167_feedback_bilingual_voice
Revises: 0166_survey_voice_note_translation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0167_feedback_bilingual_voice"
down_revision = "0166_survey_voice_note_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback_responses", sa.Column("translation_status", sa.String(length=32), nullable=True))
    op.add_column("feedback_responses", sa.Column("transcription_status", sa.String(length=32), nullable=True))
    op.add_column("feedback_responses", sa.Column("detected_language", sa.String(length=32), nullable=True))
    op.create_index("ix_feedback_responses_translation_status", "feedback_responses", ["translation_status"])
    op.create_index("ix_feedback_responses_transcription_status", "feedback_responses", ["transcription_status"])

    op.create_table(
        "feedback_voice_note_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("feedback_sessions.id"), nullable=False),
        sa.Column("response_id", sa.String(length=36), sa.ForeignKey("feedback_responses.id"), nullable=False),
        sa.Column("inbound_message_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("provider_media_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("audio_file_path", sa.Text(), nullable=True),
        sa.Column("audio_original_filename", sa.String(length=255), nullable=True),
        sa.Column("audio_mime_type", sa.String(length=128), nullable=True),
        sa.Column("transcription_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("transcription_error", sa.Text(), nullable=True),
        sa.Column("translation_status", sa.String(length=32), nullable=True),
        sa.Column("detected_language", sa.String(length=32), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcribed_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_voice_note_jobs_org_id", "feedback_voice_note_jobs", ["org_id"])
    op.create_index("ix_feedback_voice_note_jobs_session_id", "feedback_voice_note_jobs", ["session_id"])
    op.create_index("ix_feedback_voice_note_jobs_response_id", "feedback_voice_note_jobs", ["response_id"])
    op.create_index("ix_feedback_voice_note_jobs_inbound_message_id", "feedback_voice_note_jobs", ["inbound_message_id"])
    op.create_index(
        "ix_feedback_voice_note_jobs_transcription_status",
        "feedback_voice_note_jobs",
        ["transcription_status"],
    )
    op.create_index(
        "ix_feedback_voice_note_jobs_translation_status",
        "feedback_voice_note_jobs",
        ["translation_status"],
    )
    op.create_unique_constraint(
        "uq_feedback_voice_note_inbound_media",
        "feedback_voice_note_jobs",
        ["inbound_message_id", "provider_media_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_feedback_voice_note_inbound_media", "feedback_voice_note_jobs", type_="unique")
    op.drop_table("feedback_voice_note_jobs")
    op.drop_index("ix_feedback_responses_transcription_status", table_name="feedback_responses")
    op.drop_index("ix_feedback_responses_translation_status", table_name="feedback_responses")
    op.drop_column("feedback_responses", "detected_language")
    op.drop_column("feedback_responses", "transcription_status")
    op.drop_column("feedback_responses", "translation_status")
