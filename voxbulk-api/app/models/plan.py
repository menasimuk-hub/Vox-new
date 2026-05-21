from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    price_gbp_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")

    # Rich copy for marketing / clinic dashboard (optional).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of strings, e.g. ["Feature A","Feature B"]
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    calls_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    whatsapp_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sms_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overage_per_min_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trial_days_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="dental")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

