"""Push appointment confirm/reschedule/cancel outcomes back to CRM."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
import httpx
from sqlalchemy.orm import Session
from app.models.appointment import Appointment
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config

logger = logging.getLogger(__name__)
HUBSPOT_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"

def _hubspot_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat() + "Z"

def _patch_hubspot_contact(token, contact_id, properties):
    if not properties:
        return
    with httpx.Client(timeout=30.0) as client:
        res = client.patch(
            f"{HUBSPOT_CONTACTS_URL}/{contact_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"properties": properties},
        )
    if res.status_code >= 400:
        raise ValueError(f"HubSpot contact update failed: {res.text[:300]}")


def _maybe_move_hubspot_lists(
    db: Session,
    org_id: str,
    token: str,
    *,
    contact_id: str,
    status: str,
) -> None:
    from app.services.hubspot_connection_service import get_hubspot_config
    from app.services.hubspot_list_service import move_contact_between_lists

    cfg = get_hubspot_config(db, org_id)
    source_list = str(cfg.get("appointment_list_id") or "").strip() or None
    confirmed_list = str(cfg.get("appointment_confirmed_list_id") or "").strip() or None
    cancelled_list = str(cfg.get("appointment_cancelled_list_id") or "").strip() or None
    if status == "confirmed" and confirmed_list:
        move_contact_between_lists(
            token,
            contact_id=contact_id,
            remove_from_list_id=source_list if source_list != confirmed_list else None,
            add_to_list_id=confirmed_list,
        )
    elif status == "cancelled" and cancelled_list:
        move_contact_between_lists(
            token,
            contact_id=contact_id,
            remove_from_list_id=source_list if source_list != cancelled_list else None,
            add_to_list_id=cancelled_list,
        )
    elif status == "rescheduled" and confirmed_list:
        # Keep on source list unless a confirmed list is configured for completed outcomes only
        pass


def maybe_writeback_appointment_to_crm(db: Session, appt: Appointment) -> dict[str, Any]:
    source = str(appt.crm_source or "").strip().lower()
    record_id = str(appt.crm_record_id or "").strip()
    if not record_id or source not in {"hubspot"}:
        return {"skipped": True, "reason": "no_crm_record"}
    from app.services.hubspot_connection_service import _ensure_access_token, hubspot_status
    if not hubspot_status(db, appt.org_id).get("connected"):
        return {"skipped": True, "reason": "hubspot_not_connected"}
    cfg = get_config(db, appt.org_id)
    date_prop = str(cfg.get("crm_date_property") or "appointment_date").strip() or "appointment_date"
    token = _ensure_access_token(db, appt.org_id)
    properties = {}
    status = str(appt.status or "").strip().lower()
    if status == "confirmed":
        properties["voxbulk_appointment_status"] = "confirmed"
    elif status == "cancelled":
        properties["voxbulk_appointment_status"] = "cancelled"
    elif status == "rescheduled":
        properties["voxbulk_appointment_status"] = "rescheduled"
        target = appt.rescheduled_to_datetime or appt.appointment_datetime
        if isinstance(target, datetime):
            properties[date_prop] = _hubspot_datetime(target)
    if status in {"confirmed", "scheduled"} and isinstance(appt.appointment_datetime, datetime):
        properties.setdefault(date_prop, _hubspot_datetime(appt.appointment_datetime))
    if not properties:
        return {"skipped": True, "reason": "no_properties"}
    _patch_hubspot_contact(token, record_id, properties)
    try:
        _maybe_move_hubspot_lists(db, appt.org_id, token, contact_id=record_id, status=status)
    except Exception:
        logger.exception("appointment_hubspot_list_writeback_failed appointment_id=%s", appt.id)
    append_log(db, appointment_id=appt.id, event_type="crm_writeback", detail={"crm_source": source, "properties": list(properties.keys())})
    return {"ok": True, "crm_source": source, "properties": properties}
