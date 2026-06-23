"""Organisation-level AI Appointment Manager settings."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation

DEFAULT_APPOINTMENT_CONFIG: dict[str, Any] = {
    "setup_complete": False,
    "workspace_name": "",
    "crm_provider": "hubspot",
    "crm_object": "contacts",
    "crm_date_property": "appointment_date",
    "sync_interval_minutes": 60,
    "appointment_agent_id": None,
    "outreach_window_start": "09:00",
    "outreach_window_end": "16:00",
    "wa_template_name": "appt_confirm_v1",
    "wa_send_hours_before": 72,
    "call_hours_before": 24,
    "wa_enabled": True,
    "call_enabled": True,
    "reminder_sequence_json": [],
    "calendar_enabled": False,
    "calendar_id": "primary",
    "slot_duration_minutes": 30,
    "post_survey_enabled": False,
    "post_survey_order_id": None,
    "post_survey_delay_hours": 2,
    "last_crm_sync_at": None,
    "last_crm_sync_fetched": 0,
    "last_crm_sync_created": 0,
    "last_crm_sync_updated": 0,
}


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _merge_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_APPOINTMENT_CONFIG)
    for key in DEFAULT_APPOINTMENT_CONFIG:
        if key in cfg:
            out[key] = cfg[key]
    seq = out.get("reminder_sequence_json")
    out["reminder_sequence_json"] = seq if isinstance(seq, list) else []
    out["wa_enabled"] = bool(out.get("wa_enabled"))
    out["call_enabled"] = bool(out.get("call_enabled"))
    out["wa_send_hours_before"] = int(out.get("wa_send_hours_before") or DEFAULT_APPOINTMENT_CONFIG["wa_send_hours_before"])
    out["call_hours_before"] = int(out.get("call_hours_before") or DEFAULT_APPOINTMENT_CONFIG["call_hours_before"])
    out["wa_template_name"] = str(out.get("wa_template_name") or DEFAULT_APPOINTMENT_CONFIG["wa_template_name"]).strip()
    out["setup_complete"] = bool(out.get("setup_complete"))
    out["workspace_name"] = str(out.get("workspace_name") or "").strip()
    out["crm_provider"] = str(out.get("crm_provider") or DEFAULT_APPOINTMENT_CONFIG["crm_provider"]).strip()
    out["crm_object"] = str(out.get("crm_object") or DEFAULT_APPOINTMENT_CONFIG["crm_object"]).strip()
    out["crm_date_property"] = str(out.get("crm_date_property") or DEFAULT_APPOINTMENT_CONFIG["crm_date_property"]).strip()
    out["sync_interval_minutes"] = int(out.get("sync_interval_minutes") or DEFAULT_APPOINTMENT_CONFIG["sync_interval_minutes"])
    agent_id = out.get("appointment_agent_id")
    out["appointment_agent_id"] = str(agent_id).strip() if agent_id else None
    out["outreach_window_start"] = str(out.get("outreach_window_start") or DEFAULT_APPOINTMENT_CONFIG["outreach_window_start"])
    out["outreach_window_end"] = str(out.get("outreach_window_end") or DEFAULT_APPOINTMENT_CONFIG["outreach_window_end"])
    out["calendar_enabled"] = bool(out.get("calendar_enabled"))
    out["calendar_id"] = str(out.get("calendar_id") or DEFAULT_APPOINTMENT_CONFIG["calendar_id"]).strip() or "primary"
    out["slot_duration_minutes"] = int(out.get("slot_duration_minutes") or DEFAULT_APPOINTMENT_CONFIG["slot_duration_minutes"])
    out["post_survey_enabled"] = bool(out.get("post_survey_enabled"))
    survey_id = out.get("post_survey_order_id")
    out["post_survey_order_id"] = str(survey_id).strip() if survey_id else None
    out["post_survey_delay_hours"] = int(out.get("post_survey_delay_hours") or DEFAULT_APPOINTMENT_CONFIG["post_survey_delay_hours"])
    out["last_crm_sync_at"] = str(out.get("last_crm_sync_at") or "").strip() or None
    for key in ("last_crm_sync_fetched", "last_crm_sync_created", "last_crm_sync_updated"):
        try:
            out[key] = int(out.get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _validate(cfg: dict[str, Any]) -> None:
    call_h = int(cfg.get("call_hours_before") or 0)
    wa_h = int(cfg.get("wa_send_hours_before") or 0)
    if call_h >= wa_h:
        raise ValueError("call_hours_before must be less than wa_send_hours_before")


def get_config(db: Session, org_id: str) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        return dict(DEFAULT_APPOINTMENT_CONFIG)
    stored = _loads(getattr(org, "appointment_manager_config_json", None))
    return _merge_defaults(stored)


def save_config(db: Session, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    current = get_config(db, org_id)
    patch = payload if isinstance(payload, dict) else {}
    for key in DEFAULT_APPOINTMENT_CONFIG:
        if key in patch and patch[key] is not None:
            current[key] = patch[key]
    current = _merge_defaults(current)
    _validate(current)
    org.appointment_manager_config_json = json.dumps(current, ensure_ascii=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return current
