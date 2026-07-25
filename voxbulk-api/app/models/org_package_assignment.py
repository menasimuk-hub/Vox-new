"""Private org packages — plans hidden from public catalogs, assigned to specific orgs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrgPackageAssignment(Base):
    """Links an organisation to one private plan per service_kind."""

    __tablename__ = "org_package_assignments"
    __table_args__ = (UniqueConstraint("org_id", "service_kind", name="uq_org_package_assignment_org_service"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    service_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PlanUnitRate(Base):
    """Per-currency unit rates for a plan (connection / WA / CV). Null = use platform default."""

    __tablename__ = "plan_unit_rates"
    __table_args__ = (UniqueConstraint("plan_id", "currency", name="uq_plan_unit_rate_plan_currency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    connection_fee_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interview_per_min_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wa_package_fee_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wa_extra_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_scan_fee_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
