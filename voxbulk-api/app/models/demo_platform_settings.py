"""Platform settings for the public AI Demo Agent (Telnyx assistant id, etc.)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DemoPlatformSettings(Base):
    __tablename__ = "demo_platform_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    provider_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # JSON map: {"DEFAULT": "<agent_definition.id>", "GB": "...", "AU": "...", ...}
    agent_by_region_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_voice: Mapped[str | None] = mapped_column(String(80), nullable=True)
    soft_cap_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
