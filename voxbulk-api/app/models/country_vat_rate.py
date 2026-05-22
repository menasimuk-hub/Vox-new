from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CountryVatRate(Base):
    __tablename__ = "country_vat_rates"
    __table_args__ = (UniqueConstraint("country_code", name="uq_country_vat_rates_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    country_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    vat_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
