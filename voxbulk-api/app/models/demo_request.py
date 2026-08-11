"""AI Demo Agent — inbound / manual demo invite requests."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DemoRequest(Base):
    __tablename__ = "demo_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="web", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    whatsapp_e164: Mapped[str | None] = mapped_column(String(40), nullable=True)
    callback_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    website: Mapped[str] = mapped_column(String(512), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    # Admin override: GB / AU / SA / … — when set, session uses that market's agent.
    voice_region: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    conversation_memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_sales_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    frontpage_lead_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    demo_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tracking_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    link_clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
