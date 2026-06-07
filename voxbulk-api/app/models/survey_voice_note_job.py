"""Async WhatsApp voice-note transcription jobs for open-text survey answers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyVoiceNoteJob(Base):
    __tablename__ = "survey_voice_note_jobs"
    __table_args__ = (
        UniqueConstraint(
            "inbound_message_id",
            "provider_media_id",
            name="uq_survey_voice_note_inbound_media",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_order_recipients.id"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("survey_sessions.id"), nullable=True, index=True)
    whatsapp_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    answer_context: Mapped[str] = mapped_column(String(32), nullable=False, default="normal", index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    inbound_message_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_media_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    audio_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audio_file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_source: Mapped[str] = mapped_column(String(32), nullable=False, default="voice_note")
    detected_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    transcription_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcription_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transcription_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcription_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
