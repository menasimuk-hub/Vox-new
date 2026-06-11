from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(32), nullable=False, default="voxbulk", index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    pending_plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("plans.id"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    payment_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="manual_cash")
    payment_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="test")
    external_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # GoCardless mandate lifecycle
    mandate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mandate_status: Mapped[str | None] = mapped_column(String(40), nullable=True)  # active | cancelled | failed | expired
    first_payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cancellation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="none")
    cancellation_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_refund_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cancellation_requested_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancellation_support_ticket_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("support_tickets.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

