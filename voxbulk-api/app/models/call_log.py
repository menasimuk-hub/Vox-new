from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    dentally_appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("dentally_appointments.id"), nullable=True, index=True
    )
    appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointments.id"), nullable=True, index=True
    )
    patient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patients.id"), nullable=True, index=True)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="twilio")
    external_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # e.g. Twilio CallSid
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="outbound")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")

    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_stream_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    llm_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    usage_metered: Mapped[bool] = mapped_column(nullable=False, default=False)

