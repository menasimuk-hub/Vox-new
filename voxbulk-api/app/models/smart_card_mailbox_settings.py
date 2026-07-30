"""Smart Card QR outbound mailbox — From smartqr@voxbulk.com."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SMART_CARD_MAILBOX_ROW_ID = 1


class SmartCardMailboxSettings(Base):
    __tablename__ = "smart_card_mailbox_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_email: Mapped[str] = mapped_column(String(320), nullable=False, default="smartqr@voxbulk.com")
    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="VOXBULK Smart Card QR")
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
