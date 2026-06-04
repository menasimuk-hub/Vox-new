"""Platform-wide WA Survey runtime toggles (P4 AI picker)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WaSurveyPlatformSettings(Base):
    __tablename__ = "wa_survey_platform_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    ai_picker_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
