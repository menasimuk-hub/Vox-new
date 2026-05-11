from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "dedupe_key", name="uq_webhook_provider_dedupe"),
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_provider_external_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # twilio/vapi/gocardless
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)  # stable key for idempotency

    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")  # received/processing/processed/failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    raw_body: Mapped[str] = mapped_column(Text, nullable=False)

    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

