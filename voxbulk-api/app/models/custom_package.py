"""Custom multi-service private packages (Admin Products → Custom packages)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomPackage(Base):
    """One commercial deal spanning optional CF / Core / Smart Card / Expo / Survey modules."""

    __tablename__ = "custom_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # monthly | yearly
    interval: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    # GBP | USD | EUR | CAD | AUD — single currency for the whole deal
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    # Package fee in minor units of `currency` (monthly or annual depending on interval)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # draft | active | inactive
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Module toggles + quotas + overage rates (JSON)
    modules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # { mode: default|custom, core: ["GB",...], extra: ["DE",...] }
    allowlist_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Optional internal margin notes (not customer-facing)
    internal_cost_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CustomPackageOrgAssignment(Base):
    """Links organisations to a custom package (many orgs per package)."""

    __tablename__ = "custom_package_org_assignments"
    __table_args__ = (UniqueConstraint("org_id", name="uq_custom_package_org_assignment_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    custom_package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("custom_packages.id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
