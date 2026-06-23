"""Live appointment tools for Telnyx AI assistant webhook calls."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.services.appointment_availability_service import find_free_slots
from app.services.appointment_calendar_service import maybe_sync_appointment_calendar
from app.services.appointment_crm_writeback_service import maybe_writeback_appointment_to_crm
from app.services.appointment_log_service import append_log
from app.services.appointment_voice_agent_service import build_appointment_voice_config
from app.services.telnyx_voice_service import _decode_client_state

logger = logging.getLogger(__name__)

BUSY_STATUSES = frozenset({"scheduled", "confirmed", "rescheduled"})


def _parse_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Extract arguments, dynamic_variables, and call_control_id from Telnyx tool/init payloads."""
    arguments: dict[str, Any] = {}
    dynamic: dict[str, Any] = {}
    call_id = ""

    if isinstance(payload.get("arguments"), dict):
        arguments.update(payload["arguments"])
    if isinstance(payload.get("dynamic_variables"), dict):
        dynamic.update(payload["dynamic_variables"])

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    if isinstance(record, dict):
        if isinstance(record.get("arguments"), dict):
            arguments = {**arguments, **record["arguments"]}
        if isinstance(record.get("dynamic_variables"), dict):
            dynamic = {**dynamic, **record["dynamic_variables"]}
        call_id = str(
            record.get("call_control_id")
            or record.get("call_leg_id")
            or record.get("id")
            or ""
        ).strip()

    call_id = call_id or str(payload.get("call_control_id") or arguments.get("call_control_id") or "").strip()
    return arguments, dynamic, call_id


def _resolve_appointment(
    db: Session,
    *,
    arguments: dict[str, Any],
    dynamic: dict[str, Any],
    call_control_id: str,
) -> Appointment | None:
    appt_id = str(dynamic.get("appointment_id") or arguments.get("appointment_id") or "").strip()
    if appt_id:
        row = db.get(Appointment, appt_id)
        if row is not None:
            return row

    if call_control_id:
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
        if log is not None and log.appointment_id:
            row = db.get(Appointment, log.appointment_id)
            if row is not None:
                return row

        # Fallback: decode client_state on the call log payload if present
        if log is not None and log.raw_payload:
            try:
                import json

                raw = json.loads(log.raw_payload)
                state_raw = raw.get("client_state") if isinstance(raw, dict) else None
                parsed = _decode_client_state(state_raw) if isinstance(state_raw, str) else None
                if parsed:
                    appt_id = str(parsed.get("appointment_id") or "").strip()
                    if appt_id:
                        row = db.get(Appointment, appt_id)
                        if row is not None:
                            return row
            except Exception:
                pass

    org_id = str(dynamic.get("org_id") or arguments.get("org_id") or "").strip()
    phone = str(dynamic.get("contact_phone") or arguments.get("contact_phone") or "").strip()
    if org_id and phone:
        row = db.execute(
            select(Appointment)
            .where(
                Appointment.org_id == org_id,
                Appointment.contact_phone == phone,
                Appointment.status.in_(tuple(BUSY_STATUSES)),
            )
            .order_by(Appointment.appointment_datetime.asc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row
    return None


def build_initialization_response(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Telnyx assistant.initialization → inject appointment context as dynamic variables."""
    arguments, dynamic, call_id = _parse_payload(payload)
    appt = _resolve_appointment(db, arguments=arguments, dynamic=dynamic, call_control_id=call_id)
    if appt is None:
        return {"dynamic_variables": dynamic or {}}

    voice_cfg = build_appointment_voice_config(db, appt=appt, call_kind="confirmation")
    variables = {
        **dynamic,
        "appointment_id": appt.id,
        "org_id": appt.org_id,
        "company_name": voice_cfg.get("company_name") or "",
        "contact_name": appt.contact_name,
        "first_name": str(appt.contact_name or "").strip().split()[0] if str(appt.contact_name or "").strip() else "there",
        "appointment_datetime": voice_cfg.get("appointment_datetime") or "",
        "location": appt.location or "",
        "branch": appt.branch or "",
        "service_type": appt.service_type or "",
    }
    return {"dynamic_variables": variables}


def _format_slot(dt: datetime) -> str:
    return dt.strftime("%A %d %B at %H:%M")


def _parse_slot_iso(raw: str | None) -> datetime | None:
    clean = str(raw or "").strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _pick_slot_from_arguments(db: Session, appt: Appointment, arguments: dict[str, Any]) -> datetime | None:
    explicit = _parse_slot_iso(str(arguments.get("slot_iso") or arguments.get("new_datetime") or ""))
    if explicit is not None:
        return explicit

    slot_index = arguments.get("slot_index")
    slots = find_free_slots(db, appt.org_id, exclude_appointment_id=appt.id, limit=5)
    if not slots:
        return None
    if slot_index is not None:
        try:
            idx = int(slot_index)
            if 0 <= idx < len(slots):
                return slots[idx]
        except (TypeError, ValueError):
            pass
    return slots[0]


def tool_check_availability(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    arguments, dynamic, call_id = _parse_payload(payload)
    appt = _resolve_appointment(db, arguments=arguments, dynamic=dynamic, call_control_id=call_id)
    if appt is None:
        return {"status": "error", "message": "Could not find the appointment for this call."}

    limit = 5
    try:
        limit = max(1, min(8, int(arguments.get("limit") or 5)))
    except (TypeError, ValueError):
        limit = 5

    slots = find_free_slots(db, appt.org_id, exclude_appointment_id=appt.id, limit=limit)
    if not slots:
        append_log(db, appointment_id=appt.id, event_type="tool_no_slots", detail={"call_control_id": call_id})
        db.commit()
        return {
            "status": "no_slots",
            "message": "There are no free appointment slots in the next two weeks during clinic hours.",
            "slots": [],
        }

    formatted = [{"iso": s.isoformat(), "label": _format_slot(s)} for s in slots]
    append_log(
        db,
        appointment_id=appt.id,
        event_type="tool_check_availability",
        detail={"slots": [s["iso"] for s in formatted], "call_control_id": call_id},
    )
    db.commit()
    return {
        "status": "ok",
        "message": "Here are the next available times: " + "; ".join(s["label"] for s in formatted) + ".",
        "slots": formatted,
    }


def tool_confirm_appointment(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    arguments, dynamic, call_id = _parse_payload(payload)
    appt = _resolve_appointment(db, arguments=arguments, dynamic=dynamic, call_control_id=call_id)
    if appt is None:
        return {"status": "error", "message": "Could not find the appointment for this call."}

    now = datetime.utcnow()
    appt.status = "confirmed"
    appt.confirmed_at = now
    appt.confirmation_channel = "call"
    appt.call_outcome = "confirmed"
    appt.updated_at = now
    append_log(db, appointment_id=appt.id, event_type="tool_confirmed", detail={"call_control_id": call_id})
    try:
        maybe_writeback_appointment_to_crm(db, appt)
    except Exception:
        logger.exception("appointment_tool_crm_writeback_failed confirm appointment_id=%s", appt.id)
    try:
        maybe_sync_appointment_calendar(db, appt)
    except Exception:
        logger.exception("appointment_tool_calendar_sync_failed confirm appointment_id=%s", appt.id)
    db.commit()
    voice_cfg = build_appointment_voice_config(db, appt=appt, call_kind="confirmation")
    return {
        "status": "ok",
        "message": f"Perfect — your appointment on {voice_cfg.get('appointment_datetime')} is confirmed. We look forward to seeing you.",
        "appointment_status": "confirmed",
    }


def tool_reschedule_appointment(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    arguments, dynamic, call_id = _parse_payload(payload)
    appt = _resolve_appointment(db, arguments=arguments, dynamic=dynamic, call_control_id=call_id)
    if appt is None:
        return {"status": "error", "message": "Could not find the appointment for this call."}

    chosen = _pick_slot_from_arguments(db, appt, arguments)
    if chosen is None:
        return {
            "status": "no_slots",
            "message": "I couldn't find a free slot matching that request. Would another day or time work?",
        }

    now = datetime.utcnow()
    appt.rescheduled_to_datetime = chosen
    appt.status = "rescheduled"
    appt.call_outcome = "rescheduled"
    appt.updated_at = now
    append_log(
        db,
        appointment_id=appt.id,
        event_type="tool_rescheduled",
        detail={"slot": chosen.isoformat(), "call_control_id": call_id},
    )
    try:
        maybe_writeback_appointment_to_crm(db, appt)
    except Exception:
        logger.exception("appointment_tool_crm_writeback_failed reschedule appointment_id=%s", appt.id)
    try:
        maybe_sync_appointment_calendar(db, appt)
    except Exception:
        logger.exception("appointment_tool_calendar_sync_failed reschedule appointment_id=%s", appt.id)
    db.commit()
    return {
        "status": "ok",
        "message": f"Done — I've moved your appointment to {_format_slot(chosen)}.",
        "appointment_status": "rescheduled",
        "new_datetime": chosen.isoformat(),
        "new_datetime_label": _format_slot(chosen),
    }


def tool_cancel_appointment(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    arguments, dynamic, call_id = _parse_payload(payload)
    appt = _resolve_appointment(db, arguments=arguments, dynamic=dynamic, call_control_id=call_id)
    if appt is None:
        return {"status": "error", "message": "Could not find the appointment for this call."}

    now = datetime.utcnow()
    appt.status = "cancelled"
    appt.call_outcome = "cancelled"
    appt.updated_at = now
    append_log(db, appointment_id=appt.id, event_type="tool_cancelled", detail={"call_control_id": call_id})
    try:
        maybe_writeback_appointment_to_crm(db, appt)
    except Exception:
        logger.exception("appointment_tool_crm_writeback_failed cancel appointment_id=%s", appt.id)
    try:
        maybe_sync_appointment_calendar(db, appt, action="cancel")
    except Exception:
        logger.exception("appointment_tool_calendar_sync_failed cancel appointment_id=%s", appt.id)
    db.commit()
    return {
        "status": "ok",
        "message": "Your appointment has been cancelled. Thank you for letting us know.",
        "appointment_status": "cancelled",
    }


def dispatch_appointment_tool(db: Session, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(tool_name or "").strip().lower().replace("-", "_")
    if name in {"check_availability", "availability", "find_slots"}:
        return tool_check_availability(db, payload)
    if name in {"confirm_appointment", "confirm", "confirm_booking"}:
        return tool_confirm_appointment(db, payload)
    if name in {"reschedule_appointment", "reschedule", "book_slot"}:
        return tool_reschedule_appointment(db, payload)
    if name in {"cancel_appointment", "cancel"}:
        return tool_cancel_appointment(db, payload)
    return {"status": "error", "message": f"Unknown appointment tool: {tool_name}"}
