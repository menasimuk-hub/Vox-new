from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrganisationMembership(Base):
    __tablename__ = "organisation_memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Lightweight role label for onboarding / admin visibility (e.g. owner, receptionist, manager).
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Clinic dashboard first-run wizard — persisted so logout does not reset setup.
    dashboard_setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dashboard_setup_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)

