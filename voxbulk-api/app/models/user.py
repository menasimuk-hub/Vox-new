from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deletion_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    phone_verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unverified")
    twilio_outgoing_caller_id_sid: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    twilio_phone_verification_sid: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    telnyx_verified_number_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    telnyx_verification_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    telnyx_phone_verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unverified")
    telnyx_phone_verification_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telnyx_phone_verification_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telnyx_phone_verification_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone_verification_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    phone_verification_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    phone_verification_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

