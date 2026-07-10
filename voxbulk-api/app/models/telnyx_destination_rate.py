"""Telnyx destination voice/SMS rate card (local cache — no public Telnyx rate API)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelnyxDestinationRate(Base):
    """Per-country Telnyx-ish rates for allowlist cost decisions.

    Rate columns are integer **minor units of 1/10000 of the major currency**
    (e.g. USD: 50 = $0.0050). Display as ``value / 10000``.
    """

    __tablename__ = "telnyx_destination_rates"

    country_iso: Mapped[str] = mapped_column(String(2), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    dial_code: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    voice_outbound_per_min_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_inbound_per_min_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_outbound_per_msg_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_inbound_per_msg_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
