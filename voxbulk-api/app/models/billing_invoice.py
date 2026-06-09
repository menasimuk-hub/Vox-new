from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (UniqueConstraint("provider", "external_invoice_id", name="uq_invoice_provider_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="internal", index=True)
    external_invoice_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    invoice_number: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    client_email: Mapped[str] = mapped_column(String(320), nullable=False)
    amount_gbp_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subtotal_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="GBP")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="issued")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    line_items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Billing lifecycle (Phase 1+)
    kind: Mapped[str | None] = mapped_column(String(40), nullable=True)  # campaign | subscription | overage | topup
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disputed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dispute_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GoCardless Direct Debit collection state
    dd_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dd_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dd_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dd_next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
