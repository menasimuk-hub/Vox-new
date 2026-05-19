from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.patient import Patient


class AgentToolRegistry:
    @staticmethod
    def definitions(*, allow_lookup: bool, allow_booking: bool, allow_reschedule: bool, allow_cancel: bool) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if allow_lookup:
            tools.extend(
                [
                    {"type": "function", "function": {"name": "get_patient_by_phone", "description": "Find a patient by E.164 phone number."}},
                    {"type": "function", "function": {"name": "lookup_appointments", "description": "List upcoming appointments for a patient."}},
                ]
            )
        if allow_booking:
            tools.append({"type": "function", "function": {"name": "book_appointment", "description": "Request a booking action."}})
        if allow_reschedule:
            tools.append({"type": "function", "function": {"name": "reschedule_appointment", "description": "Request appointment rescheduling."}})
        if allow_cancel:
            tools.append({"type": "function", "function": {"name": "cancel_appointment", "description": "Request appointment cancellation."}})
        tools.extend(
            [
                {"type": "function", "function": {"name": "check_availability", "description": "Check appointment availability."}},
                {"type": "function", "function": {"name": "send_sms_confirmation", "description": "Send an SMS confirmation."}},
                {"type": "function", "function": {"name": "escalate_to_human", "description": "Escalate the conversation to clinic staff."}},
            ]
        )
        return tools

    @staticmethod
    def get_patient_by_phone(db: Session, *, org_id: str, phone_e164: str) -> dict[str, Any]:
        patient = db.execute(select(Patient).where(Patient.org_id == org_id, Patient.phone_e164 == phone_e164)).scalar_one_or_none()
        if patient is None:
            return {"status": "not_found"}
        return {
            "status": "ok",
            "patient": {
                "id": patient.id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "phone_e164": patient.phone_e164,
                "email": patient.email,
            },
        }

    @staticmethod
    def lookup_appointments(db: Session, *, org_id: str, patient_id: str | None = None, phone_e164: str | None = None) -> dict[str, Any]:
        if patient_id is None and phone_e164:
            found = AgentToolRegistry.get_patient_by_phone(db, org_id=org_id, phone_e164=phone_e164)
            patient_id = (found.get("patient") or {}).get("id")
        if not patient_id:
            return {"status": "not_found", "appointments": []}
        rows = list(
            db.execute(
                select(Appointment)
                .where(Appointment.org_id == org_id, Appointment.patient_id == patient_id)
                .order_by(Appointment.scheduled_start.asc())
                .limit(10)
            ).scalars()
        )
        return {
            "status": "ok",
            "appointments": [
                {
                    "id": a.id,
                    "scheduled_start": a.scheduled_start.isoformat() if isinstance(a.scheduled_start, datetime) else str(a.scheduled_start),
                    "scheduled_end": a.scheduled_end.isoformat() if a.scheduled_end else None,
                    "status": a.status,
                    "treatment_label": a.treatment_label,
                }
                for a in rows
            ],
        }

    @staticmethod
    def safe_not_available(tool_name: str) -> dict[str, Any]:
        return {
            "status": "not_available",
            "tool": tool_name,
            "message": "This action requires a confirmed clinic workflow and has been escalated to a human.",
        }
