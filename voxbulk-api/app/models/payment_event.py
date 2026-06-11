from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "external_event_id", name="uq_payment_event_provider_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="internal", index=True)
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    client_email: Mapped[str] = mapped_column(String(320), nullable=False)

    status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    event_kind: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

