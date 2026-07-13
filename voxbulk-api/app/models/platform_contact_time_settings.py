from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformContactTimeSettings(Base):
    __tablename__ = "platform_contact_time_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    calling_days: Mapped[str] = mapped_column(String(32), nullable=False, default="1,2,3,4,5")
    calling_start: Mapped[str] = mapped_column(String(8), nullable=False, default="08:00")
    calling_end: Mapped[str] = mapped_column(String(8), nullable=False, default="21:00")
    calling_fallback_tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/London")
    wa_days: Mapped[str] = mapped_column(String(32), nullable=False, default="1,2,3,4,5,6")
    wa_start: Mapped[str] = mapped_column(String(8), nullable=False, default="09:00")
    wa_end: Mapped[str] = mapped_column(String(8), nullable=False, default="20:00")
    wa_fallback_tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/London")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
