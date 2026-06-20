"""Dedupe + schedule queue for CRM deal-stage survey automation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrmSurveyAutomationEvent(Base):
    __tablename__ = "crm_survey_automation_events"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "provider",
            "external_deal_id",
            name="uq_crm_survey_automation_order_provider_deal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_deal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deal_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stage_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", index=True)
    skip_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scheduled_send_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recipient_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
