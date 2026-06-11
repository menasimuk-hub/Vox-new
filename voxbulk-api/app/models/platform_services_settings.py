"""Platform-wide default dashboard modules for all organisations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformServicesSettings(Base):
    __tablename__ = "platform_services_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    default_allowed_services_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
