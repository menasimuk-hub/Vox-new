"""Custom Org profile — a per-customer WhatsApp workspace (WA Profiles page).

Ties one organisation to its dedicated WhatsApp connection profile, optional
calling profile, billing plan, and admin contact details. Industries dedicated
to the org are linked through the existing ``industry_organisations`` table
(restricted visibility), so this row does not duplicate template data.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

STATUS_SETUP = "setup"
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"


class CustomOrgProfile(Base):
    __tablename__ = "custom_org_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    internal_ref: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    wa_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connection_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    calling_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connection_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True
    )

    contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(190), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_SETUP, index=True)
    survey_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    feedback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
