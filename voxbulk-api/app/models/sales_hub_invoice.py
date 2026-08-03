"""Admin Sales Hub invoices — commission (we pay them) or charge (they pay us)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesHubInvoice(Base):
    __tablename__ = "sales_hub_invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    # commission = we pay them | charge = they pay us
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="commission", index=True)
    customer: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    customer_tax_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="GBP")
    discount_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    tax_percent: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # new | sent | paid | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", index=True)
    commission_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commission_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminders_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # stripe | gocardless | airwallex | manual | null
    payment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesHubInvoiceItem(Base):
    __tablename__ = "sales_hub_invoice_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sales_hub_invoices.id"), nullable=False, index=True
    )
    # ai_interview | wa_survey | customer_feedback | voxbulk_expo | ""
    service_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
