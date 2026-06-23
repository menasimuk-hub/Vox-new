from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

APPOINTMENT_STATUSES = ("scheduled", "confirmed", "rescheduled", "cancelled", "no_show")
CRM_SOURCES = ("hubspot", "pipedrive", "zoho", "manual")
WA_CONFIRMATION_STATUSES = ("pending", "delivered", "read", "replied")
CALL_OUTCOMES = ("confirmed", "rescheduled", "no_answer", "voicemail")


class Appointment(Base):
    """CRM-synced appointment for WhatsApp + AI confirmation."""

    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("org_id", "crm_source", "crm_record_id", name="uq_appointments_org_crm_record"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)

    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    appointment_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/London")

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    service_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", index=True)
    crm_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual", index=True)
    crm_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    wa_confirmation_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    wa_confirmation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    call_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    call_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    rescheduled_to_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rescheduled_from_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("appointments.id"), nullable=True, index=True)

    confirmation_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    post_survey_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AppointmentLog(Base):
    __tablename__ = "appointment_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    appointment_id: Mapped[str] = mapped_column(String(36), ForeignKey("appointments.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
