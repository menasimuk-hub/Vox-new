from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LeadSalesTask(Base):
    __tablename__ = "lead_sales_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("frontpage_lead_calls.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    interest_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    callback_timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    callback_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telnyx_assistant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sales_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    call_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    call_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telnyx_conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sales_transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_promo_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_send_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
