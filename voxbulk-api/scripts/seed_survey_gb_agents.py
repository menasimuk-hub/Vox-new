#!/usr/bin/env python3
"""Seed or update default GB phone survey voice agents (female + male).

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_survey_gb_agents.py

Set SURVEY_TELNYX_ASSISTANT_ID and SURVEY_TELNYX_ASSISTANT_ID_MALE in env before running on production.
"""
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

KB_PATH = ROOT / "kb-upload-ready" / "survey" / "survey-conduct-gb.md"
DEFAULT_TELNYX = os.environ.get("SURVEY_TELNYX_ASSISTANT_ID", "").strip()
DEFAULT_TELNYX_MALE = os.environ.get("SURVEY_TELNYX_ASSISTANT_ID_MALE", DEFAULT_TELNYX).strip()

AGENTS = (
    {
        "slug": "survey-gb-amelia",
        "name": "survey_GB-Amelia",
        "voice_label": "Amelia",
        "voice_type_label": "British English · warm female",
        "telnyx_assistant_id": DEFAULT_TELNYX,
        "is_default_survey": True,
        "service_survey_role": (
            "Experienced phone survey interviewer for clinics and businesses. "
            "Friendly, concise, maximum four survey questions per call."
        ),
        "opening_disclosure": (
            "Hello {first_name}, this is {agent_name} calling on behalf of {company_name} "
            "for a short customer survey. This call is recorded for quality. "
            "Do you have two or three minutes now?"
        ),
    },
    {
        "slug": "survey-gb-james",
        "name": "survey_GB-James",
        "voice_label": "James",
        "voice_type_label": "British English · professional male",
        "telnyx_assistant_id": DEFAULT_TELNYX_MALE,
        "is_default_survey": False,
        "service_survey_role": (
            "Professional phone survey caller. Clear, respectful, and efficient — "
            "ask up to four approved survey questions in order."
        ),
        "opening_disclosure": (
            "Hello {first_name}, this is {agent_name} from {company_name}. "
            "We're running a brief survey and this call is recorded. "
            "Is now a good time — it should only take a couple of minutes?"
        ),
    },
)

SYSTEM_PROMPT = """You are {agent_name}, a British English AI phone survey caller for {company_name}.
Conduct a short customer survey — never describe this as a job interview.
Follow the approved survey script: OPENING DISCLOSURE is already spoken; continue with INTRO, then questions.
Ask at most four survey questions in order. One question at a time. Be warm and concise."""

BASE_ROLE = """British English. Warm and professional. Pause after each question.
Accept brief answers. Respect opt-out immediately."""

CALL_WORKFLOW = """After disclosure: confirm availability → ask survey questions in order (max four) → thank and close.
If unavailable, end politely. Never sell or interview."""


def _upsert_agent(db, spec: dict, *, kb_text: str, now: datetime) -> AgentDefinition:
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one_or_none()
    if agent is None:
        agent = AgentDefinition(
            name=spec["name"],
            slug=spec["slug"],
            description="GB English AI phone survey agent",
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
    agent.description = "GB English AI phone survey agent"
    agent.system_prompt = SYSTEM_PROMPT
    agent.call_workflow = CALL_WORKFLOW
    agent.voice_label = spec["voice_label"]
    agent.voice_type_label = spec["voice_type_label"]
    telnyx_id = str(spec.get("telnyx_assistant_id") or "").strip()
    if telnyx_id:
        agent.telnyx_assistant_id = telnyx_id
    agent.base_role = BASE_ROLE
    agent.service_survey_role = spec["service_survey_role"]
    agent.service_interview_role = None
    agent.opening_disclosure_template = spec["opening_disclosure"]
    agent.supports_survey = True
    agent.supports_interview = False
    agent.supports_lead_sales = False
    agent.is_default_survey = bool(spec.get("is_default_survey"))
    agent.is_default_interview = False
    agent.disclosure_for_survey = True
    agent.disclosure_for_interview = False
    agent.disclosure_mandatory = True
    agent.retry_policy_notes = "Retry once after 2 hours for busy or no answer."
        agent.interruption_behavior_notes = (
            "If interrupted during the opening disclosure, repeat the full disclosure verbatim including "
            "that the call is recorded. If interrupted during intro or a question, repeat that step from the start."
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
        default_agent: AgentDefinition | None = None
        for spec in AGENTS:
            agent = _upsert_agent(db, spec, kb_text=kb_text, now=now)
            if spec.get("is_default_survey"):
                default_agent = agent
                _clear_other_defaults(db, agent, "is_default_survey")
        db.commit()
        for spec in AGENTS:
            row = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one()
            print(f"OK: survey agent {row.id} slug={row.slug} telnyx={row.telnyx_assistant_id or '(unset)'}")
        if not DEFAULT_TELNYX:
            print("WARN: SURVEY_TELNYX_ASSISTANT_ID not set — assign Telnyx assistant IDs in Admin before launch.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
