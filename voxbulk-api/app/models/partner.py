"""Partner marketplace providers, API keys, and screening ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PartnerProvider(Base):
    __tablename__ = "partner_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="sandbox")  # sandbox|live
    mapped_org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)
    result_webhook_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    webhook_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_fee_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=1.50)
    per_minute_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    commission_pct: Mapped[float] = mapped_column(Float, nullable=False, default=18.0)
    est_cost_per_completed_gbp: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_health_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_health_message: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PartnerApiKey(Base):
    __tablename__ = "partner_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner_providers.id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="sandbox")  # sandbox|live
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PartnerScreening(Base):
    __tablename__ = "partner_screenings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner_providers.id"), nullable=False, index=True)
    partner_reference_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="sandbox")
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=True, index=True)
    recipient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_order_recipients.id"), nullable=True, index=True)
    job_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    candidate_phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    screening_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    callback_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="accepted")
    screening_link: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    estimated_completion_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    candidate_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # passed|review|rejected
    report_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    call_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_charge_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    webhook_last_error: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
