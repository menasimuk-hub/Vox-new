#!/usr/bin/env python3
"""Seed or update default GB appointment voice agents (Emily + George)."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.survey_voice_agent_service import _clear_other_defaults

KB_PATH = ROOT / "kb-upload-ready" / "appointments" / "appointment-conduct-gb.md"

DEFAULT_TELNYX_FEMALE = os.environ.get(
    "APPOINTMENT_TELNYX_ASSISTANT_ID",
    "assistant-24be3803-76e3-40e1-bfc6-a047227d0c78",
).strip()
DEFAULT_TELNYX_MALE = os.environ.get(
    "APPOINTMENT_TELNYX_ASSISTANT_ID_MALE",
    "assistant-bede370a-f58c-4864-896e-8a7aebcd02a2",
).strip()

AGENTS = (
    {
        "slug": "appointment-gb-emily",
        "name": "appointment_GB-Emily",
        "voice_label": "Emily",
        "voice_type_label": "British English · warm female",
        "telnyx_assistant_id": DEFAULT_TELNYX_FEMALE,
        "is_default_appointment": True,
        "service_appointment_role": (
            "Warm appointment coordinator for clinics and service businesses. "
            "Confirm identity and booking details, handle reschedule or cancel requests politely."
        ),
        "opening_disclosure": (
            "Hello {first_name}, this is {agent_name} calling from {company_name} "
            "about your appointment on {appointment_datetime}. "
            "This call is recorded for quality. Am I speaking with {first_name}?"
        ),
    },
    {
        "slug": "appointment-gb-george",
        "name": "appointment_GB-George",
        "voice_label": "George",
        "voice_type_label": "British English · professional male",
        "telnyx_assistant_id": DEFAULT_TELNYX_MALE,
        "is_default_appointment": False,
        "service_appointment_role": (
            "Professional appointment confirmation caller. Clear, respectful, efficient — "
            "verify the booking and help with reschedule or cancellation."
        ),
        "opening_disclosure": (
            "Hello {first_name}, this is {agent_name} from {company_name}. "
            "I'm calling to confirm your appointment on {appointment_datetime}. "
            "This call is recorded. May I confirm I'm speaking with {first_name}?"
        ),
    },
)

SYSTEM_PROMPT = """You are {agent_name}, a British English AI appointment coordinator for {company_name}.
You confirm upcoming appointments by phone — never describe this as a survey or job interview.
The OPENING DISCLOSURE is already spoken; continue with identity confirmation, then booking confirmation.
Follow the knowledge base. One question at a time. Be warm and concise.
Never invent appointment times or claim a change unless the system confirms it."""

BASE_ROLE = """British English. Warm and professional. Pause after each question.
Accept brief answers. Respect opt-out and cancellation requests immediately."""

CALL_WORKFLOW = """After disclosure: confirm identity → read appointment date/time/location → ask to confirm attendance.
If reschedule requested: ask preferred days/times; do not promise a slot until confirmed.
If cancel requested: confirm once, acknowledge, close politely.
If unavailable, offer callback and end politely."""


def _upsert_agent(db, spec: dict, *, kb_text: str, now: datetime) -> AgentDefinition:
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one_or_none()
    if agent is None:
        agent = AgentDefinition(
            name=spec["name"],
            slug=spec["slug"],
            description="GB English AI appointment confirmation agent",
            system_prompt=SYSTEM_PROMPT,
            call_workflow=CALL_WORKFLOW,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
    else:
        agent.updated_at = now

    agent.name = spec["name"]
    agent.description = "GB English AI appointment confirmation agent"
    agent.system_prompt = SYSTEM_PROMPT
    agent.call_workflow = CALL_WORKFLOW
    agent.voice_label = spec["voice_label"]
    agent.voice_type_label = spec["voice_type_label"]
    telnyx_id = str(spec.get("telnyx_assistant_id") or "").strip()
    if telnyx_id:
        agent.telnyx_assistant_id = telnyx_id
    agent.base_role = BASE_ROLE
    agent.service_appointment_role = spec["service_appointment_role"]
    agent.service_survey_role = None
    agent.service_interview_role = None
    agent.opening_disclosure_template = spec["opening_disclosure"]
    agent.supports_appointment = True
    agent.supports_survey = False
    agent.supports_interview = False
    agent.supports_lead_sales = False
    agent.is_default_appointment = bool(spec.get("is_default_appointment"))
    agent.is_default_survey = False
    agent.is_default_interview = False
    agent.disclosure_for_appointment = True
    agent.disclosure_for_survey = False
    agent.disclosure_for_interview = False
    agent.disclosure_mandatory = True
    agent.allow_lookup_tool = True
    agent.allow_reschedule_tool = True
    agent.allow_cancel_tool = True
    agent.allow_booking_tool = False
    agent.retry_policy_notes = "Retry once after 2 hours for busy or no answer."
    agent.interruption_behavior_notes = (
        "If interrupted during the opening disclosure, repeat the full disclosure verbatim including "
        "that the call is recorded. If interrupted during confirmation, repeat that step from the start."
    )
    agent.voicemail_behavior = "leave_message"
    agent.opt_out_policy_notes = "If remove me or stop calling, acknowledge, end call, never retry."
    agent.is_active = True
    if kb_text:
        agent.kb_context = kb_text[:20000]
    return agent


def main() -> None:
    kb_text = KB_PATH.read_text(encoding="utf-8") if KB_PATH.is_file() else ""
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        for spec in AGENTS:
            agent = _upsert_agent(db, spec, kb_text=kb_text, now=now)
            if spec.get("is_default_appointment"):
                _clear_other_defaults(db, agent, "is_default_appointment")
        db.commit()
        for spec in AGENTS:
            row = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one()
            print(f"OK: appointment agent {row.id} slug={row.slug} telnyx={row.telnyx_assistant_id or '(unset)'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
