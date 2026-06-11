"""Customer Feedback service — QR WhatsApp feedback (separate from Survey / Interview)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

FEEDBACK_SERVICE_CODE = "customer_feedback"
VOXBULK_SERVICE_CODE = "voxbulk"


class FeedbackIndustry(Base):
    __tablename__ = "feedback_industries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackSurveyType(Base):
    __tablename__ = "feedback_survey_types"
    __table_args__ = (UniqueConstraint("industry_id", "slug", name="uq_feedback_survey_types_industry_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_industries.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackPackage(Base):
    """Admin-configured package limits linked to a Plan row (service_kind=customer_feedback)."""

    __tablename__ = "feedback_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False, unique=True, index=True)
    market_zone: Mapped[str] = mapped_column(String(8), nullable=False, default="gb", index=True)
    max_locations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    wa_units_included: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackUsagePeriod(Base):
    __tablename__ = "feedback_usage_periods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wa_units_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wa_units_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackLocation(Base):
    __tablename__ = "feedback_locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    industry_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_industries.id"), nullable=False, index=True)
    survey_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_survey_types.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    wa_sender_country: Mapped[str] = mapped_column(String(8), nullable=False, default="gb")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackWaSender(Base):
    __tablename__ = "feedback_wa_senders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    country_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    phone_e164: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackWaTemplate(Base):
    __tablename__ = "feedback_wa_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("feedback_industries.id"), nullable=True, index=True)
    survey_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("feedback_survey_types.id"), nullable=True, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    template_key: Mapped[str] = mapped_column(String(128), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackSession(Base):
    __tablename__ = "feedback_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    location_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_locations.id"), nullable=False, index=True)
    visitor_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_charged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackResponse(Base):
    __tablename__ = "feedback_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_sessions.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    location_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_locations.id"), nullable=False, index=True)
    survey_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("feedback_survey_types.id"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(128), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
