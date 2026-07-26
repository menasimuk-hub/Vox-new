from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PromoOffer(Base):
    __tablename__ = "promo_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    offer_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dental_trial")
    plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Unified redesign fields (nullable for legacy rows).
    benefit_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redeem_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="anyone")
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_call_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    survey_contacts_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interview_contacts_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calls_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    whatsapp_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sms_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_gbp_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overage_per_min_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prospect_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    prospect_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prospect_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lead_sales_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    ai_team_prospect_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sales_rep_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    wallet_credit_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_redemptions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    redemption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    promo_offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("promo_offers.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PromoPendingDiscount(Base):
    """Held discount applied once on the next matching service checkout."""

    __tablename__ = "promo_pending_discounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    promo_offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("promo_offers.id"), nullable=False, index=True)
    service_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    discount_type: Mapped[str] = mapped_column(String(32), nullable=False)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
