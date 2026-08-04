from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesRep(Base):
    """A salesman or partner-channel account that sells via a promo code."""

    __tablename__ = "sales_reps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # salesman | partner_channel
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="salesman", index=True)
    promo_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    caller_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Percent of commission base / invoice (e.g. 15.00 = 15%). Used when commission_type is month2|percent.
    commission_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=15.0)
    # month2 | fixed | percent — drives accrual timing and calculation.
    commission_type: Mapped[str] = mapped_column(String(24), nullable=False, default="month2")
    # Flat GBP pence when commission_type == fixed.
    commission_fixed_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Legacy label; accrual uses commission_type.
    commission_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="subscription")
    # bank | paypal
    payout_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bank_holder_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_sort_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bank_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paypal_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Denormalized billing currency from country (GBP/EUR/USD/CAD/AUD).
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # Promo: wallet voucher + per-service benefits (JSON).
    promo_benefits_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Salesman months 1–6 commission tiers (JSON).
    commission_tiers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # commission_only | one_time_only | one_time_plus_commission
    commission_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="commission_only")
    # Fixed one-time bonus in minor units (rep currency).
    one_time_bonus_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Partner discount % + billing mode (JSON).
    partner_terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Mailbox configuration (Salesman Mail v1)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smtp_username: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    smtp_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    imap_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    imap_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imap_username: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    imap_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_signature: Mapped[str] = mapped_column(Text, nullable=False, default="")


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
    demo_wa_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    demo_call_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)
    offer_details: Mapped[str | None] = mapped_column(String(255), nullable=True)
    offer_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # lead | contacted | demoed | interested | won
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="lead")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesPayoutInvoice(Base):
    """Withdrawal invoice created by a sales rep against available commission."""

    __tablename__ = "sales_payout_invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="GBP")
    # submitted | paid | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted", index=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payout_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    # monthly_2nd | yearly_1mo | partner_invoice | fixed_invoice | percent_invoice
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="monthly_2nd")
    # pending | requested | paid
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payout_invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sales_payout_invoices.id"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
