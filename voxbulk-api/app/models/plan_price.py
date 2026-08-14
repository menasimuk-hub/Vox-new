from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SUPPORTED_CURRENCIES = ("GBP", "EUR", "USD", "CAD", "AUD")


class PlanPrice(Base):
    """Explicit per-currency price for a plan.

    GBP is the authoring default. Other currencies can be FX-synced from GBP unless
    ``manual_override`` is set (Admin edited that market by hand).
    """

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
    # True when Admin set this currency by hand — FX sync from GBP will skip it.
    manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PricingFxRate(Base):
    """Admin FX rates: quote units per 1 GBP. Used only to fill catalog prices — not at checkout."""

    __tablename__ = "pricing_fx_rates"

    quote_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
