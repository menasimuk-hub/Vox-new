from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_INTERVIEW, SERVICE_LEAD_SALES, SERVICE_SURVEY
from app.core.config import get_settings
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.voice_agent_platform_settings import DEFAULT_OPENING_DISCLOSURE, VoiceAgentPlatformSettings
from app.services.agent_service_resolver import resolve_agent_for_org_service
from app.services.survey_dispatch_service import _first_name, _personalize
from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id

OPT_OUT_PHRASES = (
    "remove me",
    "don't call",
    "do not call",
    "stop calling",
    "never call",
    "take me off",
    "opt out",
    "opt-out",
    "unsubscribe",
    "not interested",
    "leave me alone",
)

DEFAULT_RETRY_AFTER_SECONDS = 3600
MAX_SURVEY_RETRIES = 1


def get_platform_voice_settings(db: Session) -> VoiceAgentPlatformSettings:
    row = db.get(VoiceAgentPlatformSettings, "default")
    if row is None:
        now = datetime.utcnow()
        row = VoiceAgentPlatformSettings(
            id="default",
            opening_disclosure_template=DEFAULT_OPENING_DISCLOSURE,
            disclosure_mandatory=True,
            disclosure_for_survey=True,
            disclosure_for_interview=True,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_platform_voice_settings(db: Session, payload: dict[str, Any]) -> VoiceAgentPlatformSettings:
    row = get_platform_voice_settings(db)
    if "global_compliance_role" in payload:
        raw = payload.get("global_compliance_role")
        row.global_compliance_role = str(raw).strip() if raw is not None and str(raw).strip() else None
    if "opening_disclosure_template" in payload:
        tpl = str(payload.get("opening_disclosure_template") or "").strip()
        if tpl:
            row.opening_disclosure_template = tpl
    for key in ("disclosure_mandatory", "disclosure_for_survey", "disclosure_for_interview"):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def platform_settings_to_dict(row: VoiceAgentPlatformSettings) -> dict[str, Any]:
    return {
        "id": row.id,
        "global_compliance_role": row.global_compliance_role,
        "opening_disclosure_template": row.opening_disclosure_template,
        "disclosure_mandatory": bool(row.disclosure_mandatory),
        "disclosure_for_survey": bool(row.disclosure_for_survey),
        "disclosure_for_interview": bool(row.disclosure_for_interview),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def agent_to_voice_dict(agent: AgentDefinition) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "slug": agent.slug,
        "description": agent.description,
        "voice_label": agent.voice_label or agent.name,
        "voice_type_label": agent.voice_type_label,
        "telnyx_assistant_id": agent.telnyx_assistant_id,
        "is_active": bool(agent.is_active),
        "supports_survey": bool(agent.supports_survey),
        "supports_interview": bool(agent.supports_interview),
        "supports_lead_sales": bool(agent.supports_lead_sales),
        "is_default_survey": bool(agent.is_default_survey),
        "is_default_interview": bool(agent.is_default_interview),
        "is_default_lead_sales": bool(agent.is_default_lead_sales),
        "system_prompt": agent.system_prompt,
        "base_role": agent.base_role,
        "service_survey_role": agent.service_survey_role,
        "service_interview_role": agent.service_interview_role,
        "service_lead_sales_role": agent.service_lead_sales_role,
        "call_workflow": agent.call_workflow,
        "opening_disclosure_template": agent.opening_disclosure_template,
        "disclosure_for_survey": bool(agent.disclosure_for_survey),
        "disclosure_for_interview": bool(agent.disclosure_for_interview),
        "disclosure_mandatory": bool(agent.disclosure_mandatory),
        "retry_policy_notes": agent.retry_policy_notes,
        "interruption_behavior_notes": agent.interruption_behavior_notes,
        "voicemail_behavior": agent.voicemail_behavior,
        "opt_out_policy_notes": agent.opt_out_policy_notes,
        "knowledge_file_ids": [],
        "kb_context_cached": bool(str(agent.kb_context or "").strip()),
    }


def _service_support_field(service_key: str) -> str:
    if service_key == SERVICE_SURVEY:
        return "supports_survey"
    if service_key == SERVICE_INTERVIEW:
        return "supports_interview"
    if service_key == SERVICE_LEAD_SALES:
        return "supports_lead_sales"
    return ""


def _default_field(service_key: str) -> str:
    if service_key == SERVICE_SURVEY:
        return "is_default_survey"
    if service_key == SERVICE_INTERVIEW:
        return "is_default_interview"
    if service_key == SERVICE_LEAD_SALES:
        return "is_default_lead_sales"
    return ""


def list_agents_for_service(db: Session, *, service_key: str, org_id: str | None = None) -> list[AgentDefinition]:
    field = _service_support_field(service_key)
    if not field:
        return []
    query = select(AgentDefinition).where(
        AgentDefinition.is_active.is_(True),
        getattr(AgentDefinition, field).is_(True),
    )
    agents = list(db.execute(query.order_by(AgentDefinition.name.asc())).scalars())
    if org_id:
        assigned = resolve_agent_for_org_service(db, org_id=org_id, service_key=service_key, require_active=True)
        if assigned and assigned.id not in {a.id for a in agents}:
            agents.insert(0, assigned)
    return agents


def list_dashboard_agents_for_service(db: Session, *, service_key: str, org_id: str) -> list[dict[str, Any]]:
    agents = list_agents_for_service(db, service_key=service_key, org_id=org_id)
    assigned = resolve_agent_for_org_service(db, org_id=org_id, service_key=service_key, require_active=False)
    out: list[dict[str, Any]] = []
    default_field = _default_field(service_key) or "is_default_survey"
    for agent in agents:
        out.append(
            {
                "id": agent.id,
                "name": agent.name,
                "voice_label": agent.voice_label or agent.name,
                "voice_type_label": agent.voice_type_label,
                "is_default_for_org": bool(assigned and assigned.id == agent.id),
                "is_platform_default": bool(getattr(agent, default_field, False)),
            }
        )
    return out


def _clear_other_defaults(db: Session, agent: AgentDefinition, field: str) -> None:
    if not getattr(agent, field, False):
        return
    for row in db.execute(select(AgentDefinition).where(AgentDefinition.id != agent.id)).scalars():
        if getattr(row, field, False):
            setattr(row, field, False)
            row.updated_at = datetime.utcnow()
            db.add(row)


def resolve_survey_agent_for_order(db: Session, order: ServiceOrder, config: dict[str, Any]) -> AgentDefinition | None:
    agent_id = str(config.get("agent_id") or config.get("survey_agent_id") or "").strip()
    if agent_id:
        agent = db.get(AgentDefinition, agent_id)
        if agent and agent.is_active and agent.supports_survey:
            return agent

    assigned = resolve_agent_for_org_service(db, org_id=order.org_id, service_key=SERVICE_SURVEY, require_active=True)
    if assigned and assigned.supports_survey:
        return assigned

    default = db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.supports_survey.is_(True), AgentDefinition.is_default_survey.is_(True))
        .limit(1)
    ).scalar_one_or_none()
    if default:
        return default

    return db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.supports_survey.is_(True))
        .order_by(AgentDefinition.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def resolve_survey_telnyx_assistant_id(db: Session, order: ServiceOrder, config: dict[str, Any]) -> tuple[str, AgentDefinition | None]:
    agent = resolve_survey_agent_for_order(db, order, config)
    if agent and str(agent.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(agent.telnyx_assistant_id), agent

    configured = str(get_settings().survey_telnyx_assistant_id or "").strip()
    if configured:
        return normalize_telnyx_assistant_id(configured), agent

    from app.services.lead_sales_service import get_lead_sales_settings

    settings = get_lead_sales_settings(db)
    fallback = str(settings.telnyx_assistant_id or "").strip()
    if fallback:
        return normalize_telnyx_assistant_id(fallback), agent
    return "", agent


def _org_name_from_config(config: dict[str, Any]) -> str:
    return str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()


def _agent_display_name(agent: AgentDefinition | None) -> str:
    if agent is None:
        return "your AI assistant"
    return str(agent.voice_label or agent.name or "your AI assistant").strip()


def build_opening_disclosure(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    service_key: str = SERVICE_SURVEY,
    org_id: str | None = None,
) -> str:
    from app.services.voice_agent_runtime import resolve_opening_disclosure_template

    return resolve_opening_disclosure_template(
        db, agent=agent, config=config, service_key=service_key, org_id=org_id
    )


def build_survey_runtime_instructions(
    db: Session,
    *,
    order: ServiceOrder,
    config: dict[str, Any],
    recipient: ServiceOrderRecipient,
    agent: AgentDefinition | None,
) -> str:
    from app.services.voice_agent_runtime import build_service_runtime_instructions

    return build_service_runtime_instructions(
        db,
        order=order,
        config=config,
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_SURVEY,
    )


def build_survey_opening_greeting(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    recipient_name: str,
    org_id: str | None = None,
) -> str:
    from app.services.voice_agent_runtime import build_service_opening_greeting

    return build_service_opening_greeting(
        db,
        agent=agent,
        config=config,
        recipient_name=recipient_name,
        service_key=SERVICE_SURVEY,
        org_id=org_id,
    )


def detect_opt_out_text(text: str) -> bool:
    clean = str(text or "").lower()
    if not clean:
        return False
    return any(phrase in clean for phrase in OPT_OUT_PHRASES)


def recipient_result_dict(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def should_skip_recipient_for_opt_out(recipient: ServiceOrderRecipient) -> bool:
    if str(recipient.status or "").lower() in {"opted_out", "cancelled"}:
        return True
    result = recipient_result_dict(recipient)
    return bool(result.get("opted_out"))


def should_wait_for_retry(recipient: ServiceOrderRecipient, *, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    result = recipient_result_dict(recipient)
    next_retry = str(result.get("next_retry_at") or "").strip()
    if not next_retry:
        return False
    try:
        retry_at = datetime.fromisoformat(next_retry.replace("Z", ""))
    except ValueError:
        return False
    return now < retry_at


def resolve_survey_retry_settings(
    db: Session,
    order: ServiceOrder,
    *,
    agent: AgentDefinition | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[int, int]:
    import re

    max_retries = MAX_SURVEY_RETRIES
    delay_seconds = DEFAULT_RETRY_AFTER_SECONDS
    if agent is None:
        _, agent = resolve_survey_telnyx_assistant_id(db, order, config or {})
    notes = str(getattr(agent, "retry_policy_notes", None) or "")
    if re.search(r"\bonce\b", notes, re.I):
        max_retries = 1
    count_match = re.search(r"(\d+)\s*(?:retries?|times?)", notes, re.I)
    if count_match:
        max_retries = max(0, min(5, int(count_match.group(1))))
    hour_match = re.search(r"(\d+)\s*(?:hour|hr|hours)", notes, re.I)
    if hour_match:
        delay_seconds = int(hour_match.group(1)) * 3600
    minute_match = re.search(r"(\d+)\s*(?:minute|min|mins)", notes, re.I)
    if minute_match:
        delay_seconds = int(minute_match.group(1)) * 60
    return max_retries, delay_seconds


def schedule_recipient_retry(
    db: Session,
    recipient: ServiceOrderRecipient,
    *,
    delay_seconds: int = DEFAULT_RETRY_AFTER_SECONDS,
    max_retries: int = MAX_SURVEY_RETRIES,
) -> None:
    result = recipient_result_dict(recipient)
    retry_count = int(result.get("retry_count") or 0)
    if retry_count >= max_retries:
        return
    result["retry_count"] = retry_count + 1
    result["next_retry_at"] = (datetime.utcnow() + timedelta(seconds=delay_seconds)).isoformat()
    result["last_retry_reason"] = str(recipient.status or "")
    recipient.status = "pending"
    recipient.result_json = json.dumps(result, ensure_ascii=False)
    db.add(recipient)
    db.commit()


def mark_recipient_opted_out(
    db: Session,
    recipient: ServiceOrderRecipient,
    *,
    reason: str = "recipient_requested",
    source_text: str = "",
) -> None:
    result = recipient_result_dict(recipient)
    result.update(
        {
            "opted_out": True,
            "opt_out_reason": reason,
            "opt_out_detected_at": datetime.utcnow().isoformat(),
            "opt_out_source_text": str(source_text or "")[:500],
            "terminal_status": "opted_out",
        }
    )
    recipient.status = "opted_out"
    recipient.result_json = json.dumps(result, ensure_ascii=False)
    db.add(recipient)
    db.commit()


def clear_survey_generated_script_on_launch(config: dict[str, Any]) -> dict[str, Any]:
    """After launch, drop draft-only script fields if approved script is present."""
    out = dict(config)
    if str(out.get("approved_script") or "").strip():
        out.pop("generated_script_draft", None)
        out.pop("generated_script_at", None)
    return out
