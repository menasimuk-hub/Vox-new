from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    service_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # survey | interview
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unpaid", index=True)

    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote_total_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote_breakdown_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    run_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # manual | scheduled
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ServiceOrderRecipient(Base):
    __tablename__ = "service_order_recipients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cv_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_parsed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
