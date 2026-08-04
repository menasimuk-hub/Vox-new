"""Platform sender emails for Messaging & SMTP (domain locked to voxbulk.com)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SENDER_DOMAIN = "voxbulk.com"


class PlatformSenderEmail(Base):
    __tablename__ = "platform_sender_emails"
    __table_args__ = (UniqueConstraint("local_part", name="uq_platform_sender_local_part"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    local_part: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # e.g. sales | noreply | billing — used by resolve_outbound
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    smtp_username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    @property
    def email(self) -> str:
        return f"{self.local_part}@{SENDER_DOMAIN}"
