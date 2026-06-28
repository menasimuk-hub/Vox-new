from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesRep(Base):
    """A salesman: a dashboard user who sells VoxBulk subscriptions via a promo code."""

    __tablename__ = "sales_reps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    promo_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    caller_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # commission_kind controls payout: "subscription" = full 2nd month (monthly) / one month (yearly).
    commission_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="subscription")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesCustomer(Base):
    """A prospect/customer added by a salesman in their portal."""

    __tablename__ = "sales_customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    branches: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contact_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Funnel stage timestamps
    demo_wa_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    demo_call_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Provenance / conversion
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)
    offer_details: Mapped[str | None] = mapped_column(String(255), nullable=True)
    offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # lead | contacted | demoed | interested | won
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="lead")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesCommission(Base):
    """A commission accrued to a salesman when a linked customer pays."""

    __tablename__ = "sales_commissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    sales_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sales_customers.id"), nullable=True, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("billing_invoices.id"), nullable=True, index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="GBP")
    # kind: "monthly_2nd" (full 2nd month) | "yearly_1mo" (one month of a yearly plan)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="monthly_2nd")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | paid
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
