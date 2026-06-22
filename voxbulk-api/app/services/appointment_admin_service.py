"""Admin operations overview for AI Appointment Manager."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.models.appointment import Appointment
from app.models.organisation import Organisation
from app.services.appointment_settings_service import get_config
from app.services.org_enabled_services import org_service_maps


def _config_issues(cfg: dict[str, Any], *, has_agent: bool, crm_connected: bool) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not cfg.get("setup_complete"):
        issues.append({"level": "warn", "code": "setup_incomplete", "message": "Setup wizard not completed"})
    if not crm_connected:
        issues.append({"level": "error", "code": "crm_missing", "message": "No CRM connected"})
    if cfg.get("call_enabled") and not has_agent and not cfg.get("appointment_agent_id"):
        issues.append({"level": "error", "code": "agent_missing", "message": "AI calls enabled but no appointment agent"})
    if cfg.get("wa_enabled") and not str(cfg.get("wa_template_name") or "").strip():
        issues.append({"level": "error", "code": "wa_template_missing", "message": "WhatsApp enabled but no template selected"})
    return issues


def _crm_connected(db: Session, org_id: str, provider: str) -> bool:
    from app.services.appointment_crm_sync_service import _org_has_crm_connected

    key = str(provider or "hubspot").strip().lower()
    if key == "zoho":
        key = "zoho_crm"
    return _org_has_crm_connected(db, org_id, key)


def operations_overview(db: Session) -> dict[str, Any]:
    now = datetime.utcnow()
    soon = now + timedelta(hours=24)
    total_appts = int(db.execute(select(func.count()).select_from(Appointment)).scalar_one() or 0)
    scheduled = int(
        db.execute(select(func.count()).select_from(Appointment).where(Appointment.status == "scheduled")).scalar_one() or 0
    )
    confirmed = int(
        db.execute(select(func.count()).select_from(Appointment).where(Appointment.status == "confirmed")).scalar_one() or 0
    )
    at_risk = int(
        db.execute(
            select(func.count()).select_from(Appointment).where(
                Appointment.status == "scheduled",
                Appointment.appointment_datetime <= soon,
                Appointment.appointment_datetime >= now,
            )
        ).scalar_one()
        or 0
    )
    org_rows = list(db.execute(select(Organisation)).scalars())
    active_orgs = 0
    orgs_with_issues = 0
    for org in org_rows:
        allowed, enabled, visible = org_service_maps(org, db)
        if not visible.get("appointments"):
            continue
        active_orgs += 1
        cfg = get_config(db, org.id)
        has_agent = bool(
            db.execute(
                select(func.count()).select_from(AgentDefinition).where(
                    AgentDefinition.is_active.is_(True),
                    AgentDefinition.supports_appointment.is_(True),
                )
            ).scalar_one()
        )
        if _config_issues(cfg, has_agent=bool(has_agent), crm_connected=_crm_connected(db, org.id, cfg.get("crm_provider", ""))):
            orgs_with_issues += 1
    return {
        "total_appointments": total_appts,
        "scheduled": scheduled,
        "confirmed": confirmed,
        "at_risk_24h": at_risk,
        "active_orgs": active_orgs,
        "orgs_with_issues": orgs_with_issues,
    }


def list_organisations(db: Session) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    soon = now + timedelta(hours=24)
    out: list[dict[str, Any]] = []
    for org in db.execute(select(Organisation).order_by(Organisation.name.asc())).scalars():
        allowed, enabled, visible = org_service_maps(org, db)
        if not visible.get("appointments"):
            continue
        cfg = get_config(db, org.id)
        appt_count = int(
            db.execute(select(func.count()).select_from(Appointment).where(Appointment.org_id == org.id)).scalar_one() or 0
        )
        at_risk = int(
            db.execute(
                select(func.count()).select_from(Appointment).where(
                    Appointment.org_id == org.id,
                    Appointment.status == "scheduled",
                    Appointment.appointment_datetime <= soon,
                    Appointment.appointment_datetime >= now,
                )
            ).scalar_one()
            or 0
        )
        has_agent = bool(
            db.execute(
                select(func.count()).select_from(AgentDefinition).where(
                    AgentDefinition.is_active.is_(True),
                    AgentDefinition.supports_appointment.is_(True),
                )
            ).scalar_one()
        )
        issues = _config_issues(
            cfg,
            has_agent=has_agent,
            crm_connected=_crm_connected(db, org.id, str(cfg.get("crm_provider") or "")),
        )
        out.append(
            {
                "org_id": org.id,
                "org_name": org.display_name or org.name,
                "contact_email": org.contact_email,
                "setup_complete": bool(cfg.get("setup_complete")),
                "wa_template_name": cfg.get("wa_template_name"),
                "wa_enabled": bool(cfg.get("wa_enabled")),
                "call_enabled": bool(cfg.get("call_enabled")),
                "crm_provider": cfg.get("crm_provider"),
                "outreach_window_start": cfg.get("outreach_window_start", "09:00"),
                "outreach_window_end": cfg.get("outreach_window_end", "16:00"),
                "appointment_count": appt_count,
                "at_risk_24h": at_risk,
                "issue_count": len(issues),
                "issues": issues,
            }
        )
    out.sort(key=lambda r: (-int(r["issue_count"]), -int(r["at_risk_24h"]), r["org_name"] or ""))
    return out


def organisation_detail(db: Session, org_id: str) -> dict[str, Any] | None:
    org = db.get(Organisation, org_id)
    if org is None:
        return None
    cfg = get_config(db, org_id)
    agents = list(
        db.execute(
            select(AgentDefinition).where(
                AgentDefinition.is_active.is_(True),
                AgentDefinition.supports_appointment.is_(True),
            )
        ).scalars()
    )
    selected_agent = None
    agent_id = str(cfg.get("appointment_agent_id") or "").strip()
    for a in agents:
        if a.id == agent_id or (not agent_id and a.is_default_appointment):
            selected_agent = {"id": a.id, "name": a.name, "voice_label": a.voice_label}
            break

    appointments = list(
        db.execute(
            select(Appointment)
            .where(Appointment.org_id == org_id)
            .order_by(Appointment.appointment_datetime.asc())
            .limit(50)
        ).scalars()
    )
    appt_rows = []
    now = datetime.utcnow()
    for a in appointments:
        flags: list[str] = []
        if a.status == "scheduled" and a.appointment_datetime and a.appointment_datetime <= now + timedelta(hours=24):
            flags.append("unconfirmed_24h")
        if a.wa_confirmation_sent_at and a.status == "scheduled" and not a.confirmed_at:
            flags.append("awaiting_wa_reply")
        if a.call_triggered_at and not a.call_outcome:
            flags.append("call_in_progress")
        if a.call_outcome in {"no_answer", "voicemail"}:
            flags.append("call_failed")
        appt_rows.append(
            {
                "id": a.id,
                "contact_name": a.contact_name,
                "contact_phone": a.contact_phone,
                "appointment_datetime": a.appointment_datetime.isoformat() if a.appointment_datetime else None,
                "status": a.status,
                "crm_source": a.crm_source,
                "wa_confirmation_status": a.wa_confirmation_status,
                "call_outcome": a.call_outcome,
                "flags": flags,
            }
        )

    issues = _config_issues(
        cfg,
        has_agent=bool(agents),
        crm_connected=_crm_connected(db, org_id, str(cfg.get("crm_provider") or "")),
    )
    return {
        "org": {
            "id": org.id,
            "name": org.display_name or org.name,
            "contact_email": org.contact_email,
        },
        "config": cfg,
        "agent": selected_agent,
        "available_agents": [{"id": a.id, "name": a.name, "voice_label": a.voice_label} for a in agents],
        "wa_templates_note": "Configure UTILITY templates in Telnyx; org uses: " + str(cfg.get("wa_template_name") or "—"),
        "issues": issues,
        "appointments": appt_rows,
    }
