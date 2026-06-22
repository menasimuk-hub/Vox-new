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
    append_log(db, appointment_id=appt.id, event_type="crm_writeback", detail={"crm_source": source, "properties": list(properties.keys())})
    return {"ok": True, "crm_source": source, "properties": properties}
