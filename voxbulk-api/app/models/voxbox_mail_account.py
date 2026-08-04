"""Voxbox unified mailbox accounts (multi IMAP/SMTP)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoxboxMailAccount(Base):
    __tablename__ = "voxbox_mail_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    color: Mapped[str] = mapped_column(String(64), nullable=False, default="var(--accent-1)")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    imap_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=465)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    username: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    signature: Mapped[str] = mapped_column(Text, nullable=False, default="")
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="untested")  # untested|ok|failed
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_message: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
