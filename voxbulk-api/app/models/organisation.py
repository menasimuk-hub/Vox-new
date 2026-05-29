from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 2: organisation profile fields
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True, index=True)
    onboarding_state: Mapped[str] = mapped_column(String(40), nullable=False, default="account_created", index=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    onboarding_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    booking_software_slug: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("supported_service_apis.slug"),
        nullable=True,
        index=True,
    )

    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    county_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    survey_credits_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interview_credits_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wallet_balance_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduling_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_services_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_services_json: Mapped[str | None] = mapped_column(Text, nullable=True)

