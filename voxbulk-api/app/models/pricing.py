from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.pricing_schema import WHATSAPP_SURVEY_FEE_PENCE_COLUMN


class PricingGlobalSettings(Base):
    """Singleton row (id=1) — FX, connection fee, PAYG service rates, estimator defaults."""

    __tablename__ = "pricing_global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    fx_aud_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.95)
    fx_cad_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.71)
    fx_usd_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.26)

    connection_fee_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    connection_fee_label: Mapped[str] = mapped_column(
        String(255), nullable=False, default="AI Interview — connection fee"
    )
    connection_fee_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    interview_per_min_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=35)
    wa_survey_package_fee_pence: Mapped[int] = mapped_column(
        WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
        Integer,
        nullable=False,
        default=50,
    )
    wa_survey_extra_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=49)
    ats_cv_scan_fee_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=75)

    estimator_default_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    estimator_default_interview_count: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class TopupTier(Base):
    __tablename__ = "topup_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    credit_gbp_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_credit_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrgCustomPricing(Base):
    """Enterprise / bespoke pricing for a specific organisation."""

    __tablename__ = "org_custom_pricing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="Custom enterprise pricing")

    monthly_price_gbp_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_min_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_fee_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    minutes_included: Mapped[int | None] = mapped_column(Integer, nullable=True)
    whatsapp_included: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_scans_included: Mapped[int | None] = mapped_column(Integer, nullable=True)

    interview_per_min_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wa_survey_package_fee_pence: Mapped[int | None] = mapped_column(
        WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
        Integer,
        nullable=True,
    )
    wa_survey_extra_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ats_cv_scan_fee_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
