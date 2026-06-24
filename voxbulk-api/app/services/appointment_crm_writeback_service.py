"""Push appointment confirm/reschedule/cancel outcomes back to CRM."""
from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config

logger = logging.getLogger(__name__)
HUBSPOT_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"
HUBSPOT_OBJECTS_URL = "https://api.hubapi.com/crm/v3/objects"
HUBSPOT_PROPERTIES_URL = "https://api.hubapi.com/crm/v3/properties"
HUBSPOT_ROUTE_BUCKET_PROPERTY = "voxbulk_appointment_bucket"
PIPEDRIVE_DEALS_URL = "https://api.pipedrive.com/v1/deals"

def _hubspot_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat() + "Z"

def _patch_hubspot_contact(token: str, contact_id: str, properties: dict[str, str]) -> None:
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


def _patch_hubspot_object(token: str, object_type: str, object_id: str, properties: dict[str, str]) -> None:
    if not properties:
        return
    object_path = quote(str(object_type).strip(), safe="-_")
    object_id_path = quote(str(object_id).strip(), safe="-_")
    with httpx.Client(timeout=30.0) as client:
        res = client.patch(
            f"{HUBSPOT_OBJECTS_URL}/{object_path}/{object_id_path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"properties": properties},
        )
    if res.status_code >= 400:
        raise ValueError(f"HubSpot {object_type} update failed: {res.text[:300]}")


def _patch_pipedrive_deal(token: str, deal_id: str, properties: dict[str, str]) -> None:
    if not properties:
        return
    with httpx.Client(timeout=30.0) as client:
        res = client.put(
            f"{PIPEDRIVE_DEALS_URL}/{deal_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=properties,
        )
    if res.status_code >= 400:
        raise ValueError(f"Pipedrive deal update failed: {res.text[:300]}")


def _patch_zoho_deal(token: str, api_domain: str, deal_id: str, properties: dict[str, str]) -> None:
    if not properties:
        return
    base = f"https://{str(api_domain).strip().lstrip('https://').lstrip('http://')}"
    with httpx.Client(timeout=30.0) as client:
        res = client.put(
            f"{base}/crm/v2/Deals/{deal_id}",
            headers={"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"},
            json={"data": [properties]},
        )
    if res.status_code >= 400:
        raise ValueError(f"Zoho CRM deal update failed: {res.text[:300]}")


def _hubspot_property_exists(token: str, object_type: str, property_name: str) -> bool:
    object_path = quote(str(object_type).strip(), safe="-_")
    property_path = quote(str(property_name).strip(), safe="-_")
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{HUBSPOT_PROPERTIES_URL}/{object_path}/{property_path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if res.status_code == 200:
        return True
    if res.status_code == 404:
        return False
    raise ValueError(f"HubSpot property check failed ({object_type}.{property_name}): {res.text[:200]}")


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


def _parse_hubspot_target(record_id: str, cfg: dict[str, Any]) -> tuple[str, str]:
    object_type = "contacts"
    object_record_id = str(record_id or "").strip()
    if ":" in object_record_id:
        maybe_type, maybe_id = object_record_id.split(":", 1)
        maybe_type = maybe_type.strip().lower()
        maybe_id = maybe_id.strip()
        if maybe_type and maybe_id:
            return maybe_type, maybe_id
    configured_object = str(cfg.get("crm_object") or "").strip().lower()
    if configured_object and configured_object != "contacts":
        object_type = configured_object
    return object_type, object_record_id


def _filter_writable_properties(token: str, object_type: str, properties: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in properties.items():
        prop = str(key or "").strip()
        if not prop:
            continue
        try:
            if _hubspot_property_exists(token, object_type, prop):
                out[prop] = value
        except Exception:
            logger.exception("hubspot_property_check_failed object=%s property=%s", object_type, prop)
    return out


def _route_bucket_for_status(status: str) -> str:
    clean = str(status or "").strip().lower()
    if clean == "confirmed":
        return "confirmed"
    if clean == "cancelled":
        return "cancelled"
    if clean == "rescheduled":
        return "rescheduled"
    if clean == "no_show":
        return "no_show"
    return "source"


def _crm_mapping(cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "date_prop": str(cfg.get("crm_date_property") or "appointment_date").strip() or "appointment_date",
        "status_prop": str(cfg.get("crm_status_property") or "voxbulk_appointment_status").strip() or "voxbulk_appointment_status",
        "bucket_prop": str(cfg.get("crm_bucket_property") or HUBSPOT_ROUTE_BUCKET_PROPERTY).strip() or HUBSPOT_ROUTE_BUCKET_PROPERTY,
    }


def maybe_writeback_appointment_to_crm(db: Session, appt: Appointment) -> dict[str, Any]:
    source = str(appt.crm_source or "").strip().lower()
    record_id = str(appt.crm_record_id or "").strip()
    if not record_id or source not in {"hubspot", "pipedrive", "zoho_crm", "zoho"}:
        return {"skipped": True, "reason": "no_crm_record"}
    cfg = get_config(db, appt.org_id)
    mapping = _crm_mapping(cfg)
    date_prop = mapping["date_prop"]
    status_prop = mapping["status_prop"]
    bucket_prop = mapping["bucket_prop"]
    object_type, object_record_id = _parse_hubspot_target(record_id, cfg)
    properties = {}
    status = str(appt.status or "").strip().lower()
    if status == "confirmed":
        properties[status_prop] = "confirmed"
    elif status == "cancelled":
        properties[status_prop] = "cancelled"
    elif status == "rescheduled":
        properties[status_prop] = "rescheduled"
        target = appt.rescheduled_to_datetime or appt.appointment_datetime
        if isinstance(target, datetime):
            properties[date_prop] = _hubspot_datetime(target)
    elif status == "no_show":
        properties[status_prop] = "no_show"
    elif status == "scheduled":
        properties[status_prop] = "scheduled"
    if status in {"confirmed", "scheduled"} and isinstance(appt.appointment_datetime, datetime):
        properties.setdefault(date_prop, _hubspot_datetime(appt.appointment_datetime))
    properties[bucket_prop] = _route_bucket_for_status(status)
    if not properties:
        return {"skipped": True, "reason": "no_properties"}
    if source == "hubspot":
        from app.services.hubspot_connection_service import _ensure_access_token, hubspot_status

        if not hubspot_status(db, appt.org_id).get("connected"):
            return {"skipped": True, "reason": "hubspot_not_connected"}
        token = _ensure_access_token(db, appt.org_id)
        if not token:
            return {"skipped": True, "reason": "hubspot_no_access_token"}
        writable = _filter_writable_properties(token, object_type, properties)
        if not writable:
            return {"skipped": True, "reason": "no_writable_properties", "crm_object": object_type}
        if object_type == "contacts":
            _patch_hubspot_contact(token, object_record_id, writable)
            try:
                _maybe_move_hubspot_lists(db, appt.org_id, token, contact_id=object_record_id, status=status)
            except Exception:
                logger.exception("appointment_hubspot_list_writeback_failed appointment_id=%s", appt.id)
        else:
            _patch_hubspot_object(token, object_type, object_record_id, writable)
        append_log(
            db,
            appointment_id=appt.id,
            event_type="crm_writeback",
            detail={
                "crm_source": source,
                "crm_object": object_type,
                "crm_record_id": object_record_id,
                "properties": list(writable.keys()),
            },
        )
        return {"ok": True, "crm_source": source, "crm_object": object_type, "properties": writable}

    if source == "pipedrive":
        from app.services.pipedrive_connection_service import _ensure_access_token, pipedrive_status

        if not pipedrive_status(db, appt.org_id).get("connected"):
            return {"skipped": True, "reason": "pipedrive_not_connected"}
        token = _ensure_access_token(db, appt.org_id)
        _patch_pipedrive_deal(token, record_id, properties)
        append_log(
            db,
            appointment_id=appt.id,
            event_type="crm_writeback",
            detail={
                "crm_source": source,
                "crm_record_id": record_id,
                "properties": list(properties.keys()),
            },
        )
        return {"ok": True, "crm_source": source, "crm_object": "deals", "properties": properties}

    from app.services.zoho_crm_connection_service import _ensure_access_token, zoho_crm_status

    if not zoho_crm_status(db, appt.org_id).get("connected"):
        return {"skipped": True, "reason": "zoho_crm_not_connected"}
    token, api_domain = _ensure_access_token(db, appt.org_id)
    _patch_zoho_deal(token, api_domain, record_id, properties)
    append_log(
        db,
        appointment_id=appt.id,
        event_type="crm_writeback",
        detail={
            "crm_source": source,
            "crm_record_id": record_id,
            "properties": list(properties.keys()),
        },
    )
    return {"ok": True, "crm_source": source, "crm_object": "deals", "properties": properties}
