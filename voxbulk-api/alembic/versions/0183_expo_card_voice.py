"""Expo leads: business_card_path; expand voice-note job for STT + translation.

Revision ID: 0183_expo_card_voice
Revises: 0182_expo_duration_packages
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0183_expo_card_voice"
down_revision = "0182_expo_duration_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expo_leads", sa.Column("business_card_path", sa.Text(), nullable=True))
    op.add_column("expo_voice_note_jobs", sa.Column("response_id", sa.String(length=36), nullable=True))
    op.add_column("expo_voice_note_jobs", sa.Column("media_url", sa.Text(), nullable=True))
    op.add_column("expo_voice_note_jobs", sa.Column("original_text", sa.Text(), nullable=True))
    op.add_column("expo_voice_note_jobs", sa.Column("translated_text", sa.Text(), nullable=True))
    op.add_column("expo_voice_note_jobs", sa.Column("detected_language", sa.String(length=32), nullable=True))
    op.create_index("ix_expo_voice_note_jobs_response_id", "expo_voice_note_jobs", ["response_id"])


def downgrade() -> None:
    op.drop_index("ix_expo_voice_note_jobs_response_id", table_name="expo_voice_note_jobs")
    op.drop_column("expo_voice_note_jobs", "detected_language")
    op.drop_column("expo_voice_note_jobs", "translated_text")
    op.drop_column("expo_voice_note_jobs", "original_text")
    op.drop_column("expo_voice_note_jobs", "media_url")
    op.drop_column("expo_voice_note_jobs", "response_id")
    op.drop_column("expo_leads", "business_card_path")
