"""AI Demo Agent — magic-link sessions and live call state."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DemoSession(Base):
    __tablename__ = "demo_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hmac: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="issued", index=True)
    voice: Mapped[str | None] = mapped_column(String(80), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    active_service_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    services_explored: Mapped[str | None] = mapped_column(Text, nullable=True)
    questions_asked: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    ui_events_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    frontpage_lead_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
