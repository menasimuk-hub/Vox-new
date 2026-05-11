from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    dentally_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    phone_e164: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

