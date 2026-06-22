"""CRUD and orchestration for CRM-synced appointments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import APPOINTMENT_STATUSES, Appointment
from app.services.appointment_call_service import initiate_confirmation_call
from app.services.appointment_log_service import append_log, list_logs_for_appointment


class AppointmentService:
    @staticmethod
    def list_appointments(
        db: Session,
        org_id: str,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[Appointment]:
        stmt = select(Appointment).where(Appointment.org_id == org_id).order_by(Appointment.appointment_datetime.asc())
        if status:
            stmt = stmt.where(Appointment.status == status)
        return list(db.execute(stmt.limit(max(1, min(limit, 500)))).scalars())

    @staticmethod
    def get_appointment(db: Session, org_id: str, appointment_id: str) -> Appointment | None:
        return db.execute(
            select(Appointment).where(Appointment.id == appointment_id, Appointment.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_detail(db: Session, org_id: str, appointment_id: str) -> dict[str, Any] | None:
        appt = AppointmentService.get_appointment(db, org_id, appointment_id)
        if appt is None:
            return None
        logs = list_logs_for_appointment(db, appointment_id)
        return {"appointment": appt, "logs": logs}

    @staticmethod
    def create_appointment(db: Session, org_id: str, payload: dict[str, Any]) -> Appointment:
        now = datetime.utcnow()
        row = Appointment(
            id=str(uuid.uuid4()),
            org_id=org_id,
            contact_name=str(payload.get("contact_name") or "").strip(),
            contact_phone=str(payload.get("contact_phone") or "").strip(),
            contact_email=(str(payload.get("contact_email")).strip() or None) if payload.get("contact_email") else None,
            appointment_datetime=payload["appointment_datetime"],
            timezone=str(payload.get("timezone") or "Europe/London"),
            location=payload.get("location"),
            branch=payload.get("branch"),
            service_type=payload.get("service_type"),
            status=str(payload.get("status") or "scheduled"),
            crm_source=str(payload.get("crm_source") or "manual"),
            crm_record_id=payload.get("crm_record_id"),
            notes=payload.get("notes"),
            created_at=now,
            updated_at=now,
        )
        if not row.contact_name or not row.contact_phone:
            raise ValueError("contact_name and contact_phone are required")
        db.add(row)
        db.flush()
        append_log(db, appointment_id=row.id, event_type="created", detail={"source": row.crm_source})
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def patch_appointment(db: Session, org_id: str, appointment_id: str, payload: dict[str, Any]) -> Appointment | None:
        appt = AppointmentService.get_appointment(db, org_id, appointment_id)
        if appt is None:
            return None
        for field in (
            "contact_name",
            "contact_phone",
            "contact_email",
            "appointment_datetime",
            "timezone",
            "location",
            "branch",
            "service_type",
            "notes",
        ):
            if field in payload and payload[field] is not None:
                setattr(appt, field, payload[field])
        appt.updated_at = datetime.utcnow()
        db.add(appt)
        append_log(db, appointment_id=appt.id, event_type="updated")
        db.commit()
        db.refresh(appt)
        return appt

    @staticmethod
    def patch_status(db: Session, org_id: str, appointment_id: str, status: str) -> Appointment | None:
        clean = str(status or "").strip().lower()
        if clean not in APPOINTMENT_STATUSES:
            raise ValueError(f"Invalid status. Allowed: {', '.join(APPOINTMENT_STATUSES)}")
        appt = AppointmentService.get_appointment(db, org_id, appointment_id)
        if appt is None:
            return None
        appt.status = clean
        appt.updated_at = datetime.utcnow()
        if clean == "confirmed":
            appt.confirmed_at = datetime.utcnow()
        db.add(appt)
        append_log(db, appointment_id=appt.id, event_type="status_changed", detail={"status": clean})
        db.commit()
        db.refresh(appt)
        return appt

    @staticmethod
    def trigger_call(db: Session, org_id: str, appointment_id: str) -> dict[str, Any]:
        appt = AppointmentService.get_appointment(db, org_id, appointment_id)
        if appt is None:
            raise ValueError("Appointment not found")
        return initiate_confirmation_call(db, appt.id)
