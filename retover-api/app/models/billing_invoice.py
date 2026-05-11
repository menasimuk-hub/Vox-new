from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (UniqueConstraint("provider", "external_invoice_id", name="uq_invoice_provider_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="internal", index=True)
    external_invoice_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    client_email: Mapped[str] = mapped_column(String(320), nullable=False)
    amount_gbp_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="GBP")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="issued")

    emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

