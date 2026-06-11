from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingRefundReview(Base):
    __tablename__ = "billing_refund_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("subscriptions.id"), nullable=True, index=True)

    source_payment_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("billing_invoices.id"), nullable=True)

    requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    requested_refund_type: Mapped[str] = mapped_column(String(40), nullable=False)

    calculated_unused_value_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_wallet_credit_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_external_refund_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    wallet_transaction_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("wallet_transactions.id"), nullable=True)
    credit_note_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_notes.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
