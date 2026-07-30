"""Smart Card QR mailbox — From smartqr@voxbulk.com (SMTP out + IMAP in)."""

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
    # Optional dedicated SMTP — if unset, outbound uses platform SMTP with From override.
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # IMAP (nullable until configured; SMTP-only works without these).
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    imap_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imap_last_sync_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
