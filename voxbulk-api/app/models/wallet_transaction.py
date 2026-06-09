from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WalletTransaction(Base):
    """Append-only wallet ledger entry. amount_minor is always positive; direction tells the sign."""

    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)

    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # credit | debit
    # topup | launch_debit | campaign_refund | manual_adjustment | overage_debit
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    balance_after_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="succeeded")  # pending | succeeded | failed
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)  # stripe | airwallex | internal | manual
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
