"""Cached Voxbox mailbox messages (synced from IMAP)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
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
    # Many-recipient To headers can exceed 1KB; keep a generous VARCHAR.
    to_addrs: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    preview: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # MySQL TEXT is 64KB — HTML mail routinely exceeds that; use MEDIUMTEXT (16MB).
    body_text: Mapped[str | None] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)

    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
