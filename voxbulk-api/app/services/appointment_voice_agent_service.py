"""Runtime voice prompt assembly for appointment confirmation calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_APPOINTMENTS
from app.models.agent import AgentDefinition
from app.models.appointment import Appointment
from app.services.agent_service_resolver import resolve_agent_for_org_service
from app.services.appointment_settings_service import get_config
from app.services.survey_dispatch_service import _first_name
from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id
from app.services.voice_agent_runtime import (
    build_service_runtime_instructions,
    resolve_voice_call_company_name,
    substitute_voice_placeholders,
)


def _format_appointment_datetime(appt: Appointment) -> str:
    dt = appt.appointment_datetime
    if isinstance(dt, datetime):
        return dt.strftime("%A %d %B at %H:%M")
    return str(dt)


def build_appointment_voice_config(
    db: Session,
    *,
    appt: Appointment,
    call_kind: str,
) -> dict[str, Any]:
    cfg = get_config(db, appt.org_id)
    company = str(cfg.get("workspace_name") or "").strip()
    if not company:
        company = resolve_voice_call_company_name(db, config={}, org_id=appt.org_id)
    return {
        "company_name": company,
        "workspace_name": company,
        "appointment_datetime": _format_appointment_datetime(appt),
        "call_kind": call_kind,
        "location": appt.location or "",
        "branch": appt.branch or "",
        "service_type": appt.service_type or "",
        "contact_name": appt.contact_name,
        "appointment_agent_id": cfg.get("appointment_agent_id"),
    }


def resolve_appointment_agent(
    db: Session,
    *,
    org_id: str,
    config: dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> AgentDefinition | None:
    cfg = config or {}
    explicit = str(agent_id or cfg.get("appointment_agent_id") or "").strip()
    if explicit:
        row = db.get(AgentDefinition, explicit)
        if row and row.is_active and row.supports_appointment:
            return row

    assigned = resolve_agent_for_org_service(db, org_id=org_id, service_key=SERVICE_APPOINTMENTS, require_active=True)
    if assigned and assigned.supports_appointment:
        return assigned

    default = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_appointment.is_(True),
            AgentDefinition.is_default_appointment.is_(True),
        )
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if default:
        return default

    return db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.supports_appointment.is_(True))
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def resolve_appointment_telnyx_assistant_id(
    db: Session,
    *,
    org_id: str,
    config: dict[str, Any] | None = None,
    agent: AgentDefinition | None = None,
) -> tuple[str, AgentDefinition | None]:
    resolved = agent or resolve_appointment_agent(db, org_id=org_id, config=config)
    if resolved and str(resolved.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(resolved.telnyx_assistant_id), resolved
    return "", resolved


def build_appointment_opening_greeting(
    db: Session,
    *,
    appt: Appointment,
    agent: AgentDefinition | None,
    config: dict[str, Any],
) -> str:
    first = _first_name(appt.contact_name)
    agent_name = str((agent.voice_label if agent else None) or (agent.name if agent else None) or "your assistant").strip()
    company = str(config.get("company_name") or "").strip()
    appt_dt = str(config.get("appointment_datetime") or _format_appointment_datetime(appt)).strip()
    template = ""
    if agent and str(agent.opening_disclosure_template or "").strip():
        template = str(agent.opening_disclosure_template).strip()
    else:
        template = (
            "Hello {first_name}, this is {agent_name} calling from {company_name} "
            "about your appointment on {appointment_datetime}. This call is recorded for quality."
        )
    rendered = substitute_voice_placeholders(
        template,
        company_name=company,
        agent_name=agent_name,
        first_name=first,
    )
    return rendered.replace("{appointment_datetime}", appt_dt)


def build_appointment_runtime_instructions(
    db: Session,
    *,
    appt: Appointment,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    call_kind: str,
) -> str:
    instructions = build_service_runtime_instructions(
        db,
        order=None,
        config=config,
        recipient=None,
        agent=agent,
        service_key=SERVICE_APPOINTMENTS,
    )
    context_lines = [
        "## This call",
        f"Purpose: {call_kind.replace('_', ' ')}.",
        f"Contact: {appt.contact_name}.",
        f"Appointment: {config.get('appointment_datetime') or _format_appointment_datetime(appt)}.",
    ]
    if appt.location:
        context_lines.append(f"Location: {appt.location}.")
    if appt.branch:
        context_lines.append(f"Branch: {appt.branch}.")
    if appt.service_type:
        context_lines.append(f"Service: {appt.service_type}.")
    context_lines.append(
        "If the caller wants to reschedule, collect preferred days/times. "
        "Do not confirm a new slot is booked unless the system confirms it."
    )
    return f"{instructions}\n\n" + "\n".join(context_lines)
