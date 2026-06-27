from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SUPPORTED_CURRENCIES = ("GBP", "EUR", "USD", "CAD", "AUD")


class PlanPrice(Base):
    """Explicit per-currency price for a plan. No FX conversion — admin sets each market price."""

    __tablename__ = "plan_prices"
    __table_args__ = (UniqueConstraint("plan_id", "currency", name="uq_plan_price_plan_currency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # None = price on application (enterprise)
    monthly_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yearly_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_min_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_per_min_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PricingCurrencySettings(Base):
    """Per-currency service unit rates (connection fee, per-minute, WA survey, CV scan)."""

    __tablename__ = "pricing_currency_settings"

    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    connection_fee_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interview_per_min_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wa_package_fee_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wa_extra_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cv_scan_fee_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
