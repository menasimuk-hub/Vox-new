from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingSettings(Base):
    """Singleton row (id=1) — company identity, VAT registration, invoice numbering."""

    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="VoxBulk Ltd")
    company_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    company_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    vat_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    invoice_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="INV")
    invoice_next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    invoice_due_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
