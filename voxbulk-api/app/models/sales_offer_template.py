from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesOfferTemplate(Base):
    __tablename__ = "sales_offer_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    offer_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dental_trial")
    plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    survey_contacts_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interview_contacts_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_call_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_in_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
