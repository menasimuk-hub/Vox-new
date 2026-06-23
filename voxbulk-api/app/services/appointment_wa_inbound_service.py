"""Handle inbound WhatsApp replies for appointment confirmations."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.services.appointment_calendar_service import maybe_sync_appointment_calendar
from app.services.appointment_crm_writeback_service import maybe_writeback_appointment_to_crm
from app.services.appointment_log_service import append_log

_CONFIRM_RE = re.compile(r"\b(confirm|yes|y|1|confirmed)\b", re.I)
_CANCEL_RE = re.compile(r"\b(cancel|no|n|0|cancelled|canceled)\b", re.I)
_RESCHEDULE_RE = re.compile(r"\b(reschedule|change|move|later)\b", re.I)


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))[-15:]


def _find_pending_appointment(db: Session, *, org_id: str, from_phone: str) -> Appointment | None:
    digits = _normalize_phone(from_phone)
    if not digits:
        return None
    rows = list(
        db.execute(
            select(Appointment)
            .where(
                Appointment.org_id == org_id,
                Appointment.status.in_(("scheduled", "rescheduled")),
            )
            .order_by(Appointment.appointment_datetime.asc())
        ).scalars()
    )
    for row in rows:
        if _normalize_phone(row.contact_phone).endswith(digits[-10:]) or digits.endswith(_normalize_phone(row.contact_phone)[-10:]):
            return row
    return None


def try_handle_inbound(db: Session, from_phone: str, body: str, org_id: str) -> bool:
    text = str(body or "").strip()
    if not text:
        return False

    appt = _find_pending_appointment(db, org_id=org_id, from_phone=from_phone)
    if appt is None:
        return False

    now = datetime.utcnow()
    if _CONFIRM_RE.search(text):
        appt.status = "confirmed"
        appt.confirmed_at = now
        appt.confirmation_channel = "whatsapp"
        appt.wa_confirmation_status = "replied"
        event = "wa_confirmed"
    elif _CANCEL_RE.search(text):
        appt.status = "cancelled"
        appt.wa_confirmation_status = "replied"
        event = "wa_cancelled"
    elif _RESCHEDULE_RE.search(text):
        appt.status = "rescheduled"
        appt.wa_confirmation_status = "replied"
        event = "wa_reschedule_requested"
    else:
        return False

    appt.updated_at = now
    db.add(appt)
    append_log(db, appointment_id=appt.id, event_type=event, detail={"body": text[:500]})
    try:
        maybe_writeback_appointment_to_crm(db, appt)
    except Exception:
        pass
    try:
        action = "cancel" if appt.status == "cancelled" else "upsert"
        maybe_sync_appointment_calendar(db, appt, action=action)
    except Exception:
        pass
    db.commit()
    return True
