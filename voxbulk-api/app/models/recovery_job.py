from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RecoveryJob(Base):
    __tablename__ = "recovery_jobs"
    __table_args__ = (UniqueConstraint("org_id", "idempotency_key", name="uq_recovery_org_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    appointment_id: Mapped[str] = mapped_column(String(36), ForeignKey("appointments.id"), nullable=False, index=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)

    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="twilio")
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # e.g. Twilio CallSid
    provider_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    state: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")  # queued/calling/messaged/recovered/failed/skipped
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

