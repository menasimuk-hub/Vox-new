"""AI voice calls for appointment confirmation and rescheduling."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.services.appointment_analysis_service import process_post_call
from app.services.appointment_billing_service import AppointmentBillingError, AppointmentBillingService
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config
from app.services.messaging_log_service import normalize_e164
from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService
from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _decode_client_state, _telnyx_config
from app.services.telnyx_api_key import telnyx_outbound_caller_id

logger = logging.getLogger(__name__)

VOICE_TERMINAL = frozenset({"completed", "failed", "cancelled", "no_answer", "busy", "voicemail"})


def _resolve_appointment_agent(db: Session, org_id: str) -> AgentDefinition | None:
    row = db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.is_default_appointment.is_(True))
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return row
    return db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.supports_appointment.is_(True))
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _start_call(
    db: Session,
    *,
    appt: Appointment,
    call_kind: str,
) -> dict[str, Any]:
    cfg = get_config(db, appt.org_id)
    if not cfg.get("call_enabled"):
        return {"ok": False, "reason": "call_disabled"}

    try:
        AppointmentBillingService.assert_can_operate(db, appt.org_id)
    except AppointmentBillingError as exc:
        return {"ok": False, "reason": "billing_blocked", "detail": str(exc)}

    phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, appt.contact_phone)
    if not phone_check.get("allowed"):
        return {"ok": False, "reason": phone_check.get("reason") or "phone_not_allowed"}

    telnyx_config = _telnyx_config(db)
    from_number = telnyx_outbound_caller_id(telnyx_config)
    if not from_number:
        return {"ok": False, "reason": "caller_id_missing"}

    agent = _resolve_appointment_agent(db, appt.org_id)
    greeting = (
        f"Hello {appt.contact_name}, this is a call to {call_kind.replace('_', ' ')} "
        f"your appointment on {appt.appointment_datetime.strftime('%d %B at %H:%M')}."
    )
    instructions = str(agent.system_prompt if agent else "Confirm or reschedule the appointment politely.")

    result = TelnyxVoiceAdapter.start_outbound_call(
        to_number=normalize_e164(appt.contact_phone),
        from_number=from_number,
        config=telnyx_config,
        client_state={
            "appointment_call": True,
            "call_kind": call_kind,
            "appointment_id": appt.id,
            "org_id": appt.org_id,
            "agent_id": agent.id if agent else None,
            "telnyx_assistant_id": agent.telnyx_assistant_id if agent else None,
            "appointment_greeting": greeting,
            "appointment_instructions": instructions[:4000],
        },
    )

    now = datetime.utcnow()
    appt.call_triggered_at = now
    appt.updated_at = now
    db.add(appt)

    log = CallLog(
        org_id=appt.org_id,
        appointment_id=appt.id,
        provider="telnyx",
        external_call_id=result.external_id,
        direction="outbound",
        status=result.status if result.ok else "failed",
        to_number=appt.contact_phone,
        from_number=from_number,
        raw_payload=json.dumps({"call_kind": call_kind, "detail": result.detail}, ensure_ascii=False),
        created_at=now,
    )
    db.add(log)
    append_log(
        db,
        appointment_id=appt.id,
        event_type=f"call_{call_kind}_started",
        detail={"ok": result.ok, "call_control_id": result.external_id},
    )
    db.commit()

    return {"ok": result.ok, "call_control_id": result.external_id, "status": result.status}


def initiate_confirmation_call(db: Session, appointment_id: str) -> dict[str, Any]:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ValueError("Appointment not found")
    return _start_call(db, appt=appt, call_kind="confirmation")


def initiate_reschedule_call(db: Session, appointment_id: str) -> dict[str, Any]:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ValueError("Appointment not found")
    return _start_call(db, appt=appt, call_kind="reschedule")


def handle_appointment_telnyx_event(db: Session, payload: dict[str, Any]) -> bool:
    """Return True if payload was handled as an appointment voice call."""
    data = payload.get("data") or payload
    event_type = str(data.get("event_type") or payload.get("event_type") or "").lower()
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    call_id = str(record.get("call_control_id") or record.get("call_leg_id") or record.get("id") or "").strip()
    if not call_id:
        return False

    client_state_raw = record.get("client_state")
    parsed = _decode_client_state(client_state_raw) if isinstance(client_state_raw, str) else None
    if not parsed or not parsed.get("appointment_call"):
        return False

    appointment_id = str(parsed.get("appointment_id") or "").strip()
    appt = db.get(Appointment, appointment_id) if appointment_id else None
    if appt is None:
        return True

    log = db.execute(select(CallLog).where(CallLog.external_call_id == call_id)).scalar_one_or_none()
    transcript = str(record.get("transcription") or record.get("transcript") or "").strip()
    if log is not None and transcript:
        log.transcript_text = transcript
        db.add(log)

    terminal = event_type in {"call.hangup", "call.ended", "call.completed"} or str(record.get("call_state") or "").lower() in VOICE_TERMINAL
    if terminal:
        now = datetime.utcnow()
        hangup_cause = str(record.get("hangup_cause") or record.get("sip_hangup_cause") or "").lower()
        if "no_answer" in hangup_cause or "busy" in hangup_cause:
            outcome = "no_answer"
        elif "voicemail" in hangup_cause or "machine" in hangup_cause:
            outcome = "voicemail"
        else:
            prior = str(log.transcript_text or "") if log is not None else ""
            analysis = process_post_call(db, appointment=appt, transcript=transcript or prior)
            outcome = str(analysis.get("outcome") or "confirmed")
            if analysis.get("rescheduled_to"):
                appt.rescheduled_to_datetime = analysis.get("rescheduled_to")
                appt.status = "rescheduled"
            elif outcome == "confirmed":
                appt.status = "confirmed"
                appt.confirmed_at = now
                appt.confirmation_channel = "call"
            elif outcome == "cancelled":
                appt.status = "cancelled"

        appt.call_outcome = outcome if outcome in {"confirmed", "rescheduled", "no_answer", "voicemail"} else "confirmed"
        appt.updated_at = now
        db.add(appt)
        append_log(db, appointment_id=appt.id, event_type="call_completed", detail={"outcome": appt.call_outcome, "event_type": event_type})
        db.commit()

    return True
