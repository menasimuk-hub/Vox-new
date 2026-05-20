from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformService(Base):
    __tablename__ = "platform_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="order")  # order | subscription
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ServicePricingRule(Base):
    __tablename__ = "service_pricing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("platform_services.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="default")  # whatsapp|call|ai_call|zoom|base|bundle
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # flat_per_order|per_person|bundle|flat_plus_per_person
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    base_fee_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bundle_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bundle_price_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_unit_price_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="GBP")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
