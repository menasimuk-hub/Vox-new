from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrgUsagePeriod(Base):
    __tablename__ = "org_usage_periods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calls_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    whatsapp_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    whatsapp_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sms_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sms_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cv_scans_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cv_scans_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pack_credits_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pack_credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pack_credits_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    overage_per_min_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overage_invoiced_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_overage_invoice_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    warned_at_80: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
