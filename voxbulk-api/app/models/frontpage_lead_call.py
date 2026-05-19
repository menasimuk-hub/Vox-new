from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FrontpageLeadCall(Base):
    __tablename__ = "frontpage_lead_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lead_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="frontpage_talk_to_us", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created", index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    voice_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    recording_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
