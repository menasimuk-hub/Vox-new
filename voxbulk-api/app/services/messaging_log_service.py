from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dentally_appointment import DentallyAppointment
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
                select(DentallyAppointment.id).where(DentallyAppointment.id == appointment_id, DentallyAppointment.org_id == org_id)
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
                DentallyAppointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == CallLog.patient_id)
            .outerjoin(DentallyAppointment, DentallyAppointment.id == CallLog.dentally_appointment_id)
            .outerjoin(Branch, Branch.id == DentallyAppointment.branch_id)
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
                    "appointment_id": log.dentally_appointment_id,
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
                DentallyAppointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == WhatsAppLog.patient_id)
            .outerjoin(DentallyAppointment, DentallyAppointment.id == WhatsAppLog.dentally_appointment_id)
            .outerjoin(Branch, Branch.id == DentallyAppointment.branch_id)
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
                    "appointment_id": log.dentally_appointment_id,
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
    def list_platform_message_logs(
        db: Session,
        *,
        limit: int = 100,
        date_from: str | None = None,
        date_to: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
        q: str | None = None,
        provider: str | None = None,
    ) -> list[dict]:
        from datetime import datetime

        from sqlalchemy import select

        stmt = select(WhatsAppLog).order_by(WhatsAppLog.id.desc()).limit(max(1, min(limit, 500)))
        rows = db.execute(stmt).scalars().all()
        out: list[dict] = []
        needle = str(q or "").strip().lower()
        from_filter = str(from_number or "").strip()
        to_filter = str(to_number or "").strip()
        provider_filter = str(provider or "").strip().lower()
        start = None
        end = None
        if date_from:
            try:
                start = datetime.fromisoformat(str(date_from).replace("Z", "+00:00"))
            except Exception:
                start = None
        if date_to:
            try:
                end = datetime.fromisoformat(str(date_to).replace("Z", "+00:00"))
            except Exception:
                end = None
        for row in rows:
            if provider_filter and str(row.provider or "").lower() != provider_filter:
                continue
            if start and row.created_at and row.created_at < start:
                continue
            if end and row.created_at and row.created_at > end:
                continue
            if from_filter and from_filter not in str(row.from_number or ""):
                continue
            if to_filter and to_filter not in str(row.to_number or ""):
                continue
            body = str(row.body or "")
            if needle and needle not in body.lower() and needle not in str(row.from_number or "").lower() and needle not in str(row.to_number or "").lower():
                continue
            delivery_error = None
            if "Delivery error:" in body:
                delivery_error = body.split("Delivery error:", 1)[1].strip().split("\n")[0].strip()
            out.append(
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
                    "delivery_error": delivery_error,
                    "created_at": row.created_at,
                }
            )
        return out

    @staticmethod
    def find_cross_provider_inbound_duplicate(
        db: Session,
        *,
        from_number: str | None,
        body: str | None,
        current_provider: str,
        window_seconds: int = 120,
    ) -> WhatsAppLog | None:
        from datetime import datetime, timedelta

        from_n = str(from_number or "").strip()
        body_n = str(body or "").strip()
        if not from_n or not body_n:
            return None
        cutoff = datetime.utcnow() - timedelta(seconds=max(30, int(window_seconds)))
        candidates = list(
            db.execute(
                select(WhatsAppLog)
                .where(WhatsAppLog.direction == "inbound")
                .where(WhatsAppLog.from_number == from_n)
                .where(WhatsAppLog.provider != str(current_provider or "").strip())
                .where(WhatsAppLog.created_at >= cutoff)
                .order_by(WhatsAppLog.created_at.desc())
                .limit(8)
            ).scalars()
        )
        for row in candidates:
            existing_body = str(row.body or "").strip()
            if existing_body == body_n or body_n in existing_body or existing_body in body_n:
                return row
        return None

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
