"""Support mailbox — support@voxbulk.com (SMTP out + IMAP in → tickets)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SUPPORT_MAILBOX_ROW_ID = 1


class SupportMailboxSettings(Base):
    __tablename__ = "support_mailbox_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox_email: Mapped[str] = mapped_column(String(320), nullable=False, default="support@voxbulk.com")
    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="VOXBULK Support")
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional dedicated SMTP — if unset, outbound uses platform SMTP with From override.
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    imap_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_sync_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
