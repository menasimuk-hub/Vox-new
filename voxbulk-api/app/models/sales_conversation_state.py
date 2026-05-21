from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesConversationState(Base):
    __tablename__ = "sales_conversation_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_sales_task_id: Mapped[str] = mapped_column(String(36), ForeignKey("lead_sales_tasks.id"), nullable=False, index=True)
    promo_offer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("promo_offers.id"), nullable=True, index=True)
    prospect_phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    prospect_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    automation_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opt_in_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    followup_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    followup_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_inbound_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
