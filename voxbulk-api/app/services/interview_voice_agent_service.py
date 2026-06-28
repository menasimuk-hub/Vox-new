"""Interview voice agents — mirrors survey agent resolution for SERVICE_INTERVIEW."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_INTERVIEW
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.agent_service_resolver import resolve_agent_for_org_service
from app.services.survey_voice_agent_service import (
    MAX_SURVEY_RETRIES,
    DEFAULT_RETRY_AFTER_SECONDS,
    detect_opt_out_text,
    mark_recipient_opted_out,
    recipient_result_dict,
    schedule_recipient_retry,
    should_skip_recipient_for_opt_out,
    should_wait_for_retry,
)
from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id
from app.core.config import get_settings


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_meeting_interview_order(order: ServiceOrder) -> bool:
    if order.service_code != "interview":
        return False
    config = _order_config(order)
    return str(config.get("delivery") or "").strip().lower() == "ai_meeting"


def is_ai_call_interview_order(order: ServiceOrder) -> bool:
    if order.service_code != "interview":
        return False
    config = _order_config(order)
    delivery = str(config.get("delivery") or "ai_call").strip().lower()
    return delivery in {"ai_call", "call", ""}


def resolve_interview_agent_for_order(db: Session, order: ServiceOrder, config: dict[str, Any]) -> AgentDefinition | None:
    agent_id = str(config.get("agent_id") or config.get("interview_agent_id") or "").strip()
    if agent_id:
        agent = db.get(AgentDefinition, agent_id)
        if agent and agent.is_active and agent.supports_interview:
            return agent

    from app.services.meeting_room_settings_service import MeetingRoomSettingsService

    meeting_agent_id = MeetingRoomSettingsService.get_settings(db).get("agent_id")
    if meeting_agent_id:
        agent = db.get(AgentDefinition, meeting_agent_id)
        if agent and agent.is_active and agent.supports_interview:
            return agent

    assigned = resolve_agent_for_org_service(db, org_id=order.org_id, service_key=SERVICE_INTERVIEW, require_active=True)
    if assigned and assigned.supports_interview:
        return assigned

    default = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_interview.is_(True),
            AgentDefinition.is_default_interview.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if default:
        return default

    return db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.is_active.is_(True), AgentDefinition.supports_interview.is_(True))
        .order_by(AgentDefinition.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def resolve_interview_telnyx_assistant_id(
    db: Session, order: ServiceOrder, config: dict[str, Any]
) -> tuple[str, AgentDefinition | None]:
    agent = resolve_interview_agent_for_order(db, order, config)
    if agent and str(agent.telnyx_assistant_id or "").strip():
        assistant_id = normalize_telnyx_assistant_id(agent.telnyx_assistant_id)
        try:
            from app.services.telnyx_assistant_service import fetch_telnyx_assistant

            fetch_telnyx_assistant(db, assistant_id)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "interview_telnyx_assistant_verify_failed agent=%s assistant_id=%s",
                agent.id,
                assistant_id,
            )
        return assistant_id, agent

    configured = str(get_settings().interview_telnyx_assistant_id or "").strip()
    if configured:
        return normalize_telnyx_assistant_id(configured), agent
    return "", agent


def build_interview_runtime_instructions(
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
        service_key=SERVICE_INTERVIEW,
    )


def build_interview_opening_greeting(
    db: Session,
    *,
    agent: AgentDefinition | None,
    config: dict[str, Any],
    recipient_name: str,
    org_id: str | None = None,
    order: ServiceOrder | None = None,
) -> str:
    from app.services.voice_agent_runtime import build_service_opening_greeting

    return build_service_opening_greeting(
        db,
        agent=agent,
        config=config,
        recipient_name=recipient_name,
        service_key=SERVICE_INTERVIEW,
        org_id=org_id,
        order=order,
    )


def resolve_interview_retry_settings(
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
        _, agent = resolve_interview_telnyx_assistant_id(db, order, config or {})
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


def clear_interview_generated_script_on_launch(config: dict[str, Any]) -> dict[str, Any]:
    out = dict(config)
    if str(out.get("approved_script") or "").strip():
        out.pop("generated_script_draft", None)
        out.pop("generated_script_at", None)
    return out
