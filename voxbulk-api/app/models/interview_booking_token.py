from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewBookingToken(Base):
    __tablename__ = "interview_booking_tokens"
    __table_args__ = (UniqueConstraint("token", name="uq_interview_booking_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_order_recipients.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    booked_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    booked_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    wa_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
