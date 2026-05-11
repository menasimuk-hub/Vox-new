from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    patient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patients.id"), nullable=True, index=True)
    dentally_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    scheduled_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled")

    # Real appointment value (in pence) if known from source system/manual input.
    value_gbp_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Treatment / appointment type label (from Dentally when available).
    treatment_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    recovery_state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    recovery_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recovery_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

