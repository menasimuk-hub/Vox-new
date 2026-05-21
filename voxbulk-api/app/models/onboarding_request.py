from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OnboardingRequest(Base):
    __tablename__ = "onboarding_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    promo_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False, default="bank_transfer")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)  # pending|approved|rejected
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

