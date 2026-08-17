from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("org_id", "service_code", "live_slot", name="uq_subscriptions_org_service_live"),
    )

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

    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_billing_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    amount_next_payment_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    billing_interval: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    # Seat quantity for service_code=smart_card (yearly per-seat packages).
    seat_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Seats included in the next charge (may lag seat_quantity while new seats are free).
    billable_seat_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When pending free seats become billable (option A: new seats free 30 days).
    added_seats_free_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tax_rate_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tax_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # 1 while status is live (active/trial/past_due/suspended/…); NULL when cancelled so many ended rows can coexist.
    live_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_advanced_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

