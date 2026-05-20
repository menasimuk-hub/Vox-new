from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.call_log import CallLog
from app.models.patient import Patient
from app.models.whatsapp_log import WhatsAppLog


def normalize_e164(raw: str) -> str:
    phone = "".join(ch for ch in str(raw or "").strip() if ch.isdigit() or ch == "+")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"
    digits = phone[1:] if phone.startswith("+") else phone
    if not phone.startswith("+") or not digits.isdigit() or not (8 <= len(digits) <= 15):
        raise ValueError("Phone number must be in E.164 format, for example +447700900123")
    return phone


class LogService:
    @staticmethod
    def _validate_optional_relations(
        db: Session,
        org_id: str,
        *,
        appointment_id: str | None = None,
        patient_id: str | None = None,
    ) -> None:
        if appointment_id:
            ok = db.execute(
                select(Appointment.id).where(Appointment.id == appointment_id, Appointment.org_id == org_id)
            ).scalar_one_or_none()
            if ok is None:
                raise ValueError("Invalid appointment_id for tenant")
        if patient_id:
            ok = db.execute(select(Patient.id).where(Patient.id == patient_id, Patient.org_id == org_id)).scalar_one_or_none()
            if ok is None:
                raise ValueError("Invalid patient_id for tenant")

    @staticmethod
    def list_call_logs(db: Session, org_id: str) -> list[CallLog]:
        rows = db.execute(
            select(
                CallLog,
                Patient.first_name,
                Patient.last_name,
                Branch.name,
                Appointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == CallLog.patient_id)
            .outerjoin(Appointment, Appointment.id == CallLog.appointment_id)
            .outerjoin(Branch, Branch.id == Appointment.branch_id)
            .where(CallLog.org_id == org_id)
            .order_by(CallLog.id.desc())
            .limit(200)
        ).all()

        out: list[dict] = []
        for log, p_first, p_last, branch_name, appt_start in rows:
            patient_name = None
            if p_first or p_last:
                patient_name = f"{p_first or ''} {p_last or ''}".strip() or None
            out.append(
                {
                    "id": log.id,
                    "org_id": log.org_id,
                    "user_id": log.user_id,
                    "appointment_id": log.appointment_id,
                    "patient_id": log.patient_id,
                    "patient_name": patient_name,
                    "branch_name": branch_name,
                    "appointment_scheduled_start": appt_start,
                    "provider": log.provider,
                    "external_call_id": log.external_call_id,
                    "direction": log.direction,
                    "status": log.status,
                    "to_number": log.to_number,
                    "from_number": log.from_number,
                    "recording_url": log.recording_url,
                    "media_stream_id": log.media_stream_id,
                    "llm_prompt": log.llm_prompt,
                    "llm_response": log.llm_response,
                    "transcript_text": log.transcript_text,
                    "raw_payload": log.raw_payload,
                    "created_at": log.created_at,
                    "started_at": log.started_at,
                    "answered_at": log.answered_at,
                    "ended_at": log.ended_at,
                    "last_status_at": log.last_status_at,
                }
            )
        return out  # type: ignore[return-value]

    @staticmethod
    def create_call_log(db: Session, org_id: str, **kwargs) -> CallLog:
        LogService._validate_optional_relations(
            db, org_id, appointment_id=kwargs.get("appointment_id"), patient_id=kwargs.get("patient_id")
        )
        obj = CallLog(org_id=org_id, **kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get_call_log(db: Session, org_id: str, log_id: int) -> CallLog | None:
        return db.execute(select(CallLog).where(CallLog.id == log_id, CallLog.org_id == org_id)).scalar_one_or_none()

    @staticmethod
    def list_whatsapp_logs(db: Session, org_id: str) -> list[WhatsAppLog]:
        rows = db.execute(
            select(
                WhatsAppLog,
                Patient.first_name,
                Patient.last_name,
                Branch.name,
                Appointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == WhatsAppLog.patient_id)
            .outerjoin(Appointment, Appointment.id == WhatsAppLog.appointment_id)
            .outerjoin(Branch, Branch.id == Appointment.branch_id)
            .where(WhatsAppLog.org_id == org_id)
            .order_by(WhatsAppLog.id.desc())
            .limit(200)
        ).all()

        out: list[dict] = []
        for log, p_first, p_last, branch_name, appt_start in rows:
            patient_name = None
            if p_first or p_last:
                patient_name = f"{p_first or ''} {p_last or ''}".strip() or None
            out.append(
                {
                    "id": log.id,
                    "org_id": log.org_id,
                    "appointment_id": log.appointment_id,
                    "patient_id": log.patient_id,
                    "patient_name": patient_name,
                    "branch_name": branch_name,
                    "appointment_scheduled_start": appt_start,
                    "provider": log.provider,
                    "external_message_id": log.external_message_id,
                    "status": log.status,
                    "direction": log.direction,
                    "to_number": log.to_number,
                    "from_number": log.from_number,
                    "body": log.body,
                    "media_json": log.media_json,
                    "raw_payload": log.raw_payload,
                    "created_at": log.created_at,
                }
            )
        return out  # type: ignore[return-value]

    @staticmethod
    def list_platform_message_logs(db: Session, *, limit: int = 100) -> list[dict]:
        rows = db.execute(select(WhatsAppLog).order_by(WhatsAppLog.id.desc()).limit(max(1, min(limit, 500)))).scalars().all()
        return [
            {
                "id": row.id,
                "org_id": row.org_id,
                "provider": row.provider,
                "external_message_id": row.external_message_id,
                "status": row.status,
                "direction": row.direction,
                "to_number": row.to_number,
                "from_number": row.from_number,
                "body": row.body,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    @staticmethod
    def create_whatsapp_log(db: Session, org_id: str, **kwargs) -> WhatsAppLog:
        LogService._validate_optional_relations(
            db, org_id, appointment_id=kwargs.get("appointment_id"), patient_id=kwargs.get("patient_id")
        )
        obj = WhatsAppLog(org_id=org_id, provider=str(kwargs.pop("provider", "telnyx")), **kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get_whatsapp_log(db: Session, org_id: str, log_id: int) -> WhatsAppLog | None:
        return db.execute(select(WhatsAppLog).where(WhatsAppLog.id == log_id, WhatsAppLog.org_id == org_id)).scalar_one_or_none()
