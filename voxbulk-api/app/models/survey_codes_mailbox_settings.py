from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SURVEY_CODES_MAILBOX_ROW_ID = 1


class SurveyCodesMailboxSettings(Base):
    """Outbound From for AI follow-up promo codes (survey.codes@voxbulk.com)."""

    __tablename__ = "survey_codes_mailbox_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_email: Mapped[str] = mapped_column(String(320), nullable=False, default="survey.codes@voxbulk.com")
    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="VOXBULK Survey Codes")
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
