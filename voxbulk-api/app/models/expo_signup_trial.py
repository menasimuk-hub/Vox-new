"""Silent Expo signup trial — one free 3-day booth per company email domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExpoCompanyDomainClaim(Base):
    """Email domains that have already received the silent Expo signup trial."""

    __tablename__ = "expo_company_domain_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email_domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    claimed_email: Mapped[str] = mapped_column(String(320), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    entitlement_consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_booth_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ExpoSignupEntitlement(Base):
    """Per-org entitlement for one free Expo 3-day package activation."""

    __tablename__ = "expo_signup_entitlements"
    __table_args__ = (UniqueConstraint("org_id", name="uq_expo_signup_entitlements_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_booth_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
