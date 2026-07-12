"""Survey AI follow-up jobs — WA Survey voice callbacks after low ratings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyAiFollowUpJob(Base):
    __tablename__ = "survey_ai_follow_up_jobs"
    __table_args__ = (UniqueConstraint("recipient_id", name="uq_survey_ai_follow_up_recipient"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_order_recipients.id"), nullable=False, index=True
    )
    visitor_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    business_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promo_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
