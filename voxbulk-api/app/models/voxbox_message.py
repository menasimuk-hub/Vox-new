"""Cached Voxbox mailbox messages (synced from IMAP)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoxboxMessage(Base):
    __tablename__ = "voxbox_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("voxbox_mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    internet_message_id: Mapped[str] = mapped_column(String(500), nullable=False, default="", index=True)
    imap_uid: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    folder: Mapped[str] = mapped_column(String(32), nullable=False, default="inbox", index=True)

    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    to_addrs: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    preview: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
