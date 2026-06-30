#!/usr/bin/env python3
"""Seed/update the 'sales ai survey' demo agent (a copy of Amelia).

This agent powers the salesman "Call & Survey" demo button: a warm 3-question
phone survey with a gentle "why weren't you happy?" follow-up. Salesmen never
write questions — the script is fixed here.

Usage (from voxbulk-api, project venv):
  python scripts/seed_sales_ai_survey_agent.py

It reuses the same Telnyx AI assistant as Amelia (slug survey-gb-amelia), or
SURVEY_TELNYX_ASSISTANT_ID if Amelia is not seeded yet.
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

SALES_AGENT_SLUG = "sales-ai-survey"
SALES_AGENT_NAME = "sales_ai_survey"
AMELIA_SLUG = "survey-gb-amelia"

# The fixed 3-question demo survey (warm welcome -> 3 questions -> warm thanks),
# with a polite follow-up when the customer is not happy.
DEMO_SURVEY_QUESTIONS = (
    "Overall, how would you rate your experience with us today — excellent, good, or poor?",
    "What did you enjoy most about your experience?",
    "Is there anything we could do to make it better next time?",
)

SYSTEM_PROMPT = """You are Joe, a warm British English AI phone survey caller for {company_name}.
This is a short, friendly customer survey — never a job interview and never a sales pitch.
Greet the customer warmly, then ask EXACTLY these three questions, one at a time, in order:
1. Overall, how would you rate your experience with us today — excellent, good, or poor?
2. What did you enjoy most about your experience?
3. Is there anything we could do to make it better next time?
If the customer sounds unhappy or answers "poor" / negatively, stay warm and empathetic,
briefly acknowledge it, and gently ask why so we can improve — do not argue or defend.
Keep it brief, one question at a time, accept short answers, and thank them warmly at the end."""

SERVICE_SURVEY_ROLE = (
    "Warm, friendly demo phone survey caller. Asks exactly three fixed questions, "
    "gently asks why if the customer is unhappy, and thanks them warmly. Never sells, never interviews."
)

OPENING_DISCLOSURE = (
    "Hello {first_name}, this is Joe calling on behalf of {company_name} for a quick, friendly "
    "customer survey — it only takes a minute and the call is recorded for quality. "
    "Is now a good time?"
)

BASE_ROLE = """British English. Warm, upbeat, and concise. Pause after each question.
Accept brief answers. If the customer is unhappy, be kind and ask why. Respect opt-out immediately."""

CALL_WORKFLOW = """After the warm welcome and disclosure: confirm it's a good time ->
ask the three fixed questions in order -> if the customer is unhappy, kindly ask why ->
thank them warmly and close. Never sell. Never interview."""


def _resolve_telnyx_assistant_id(db) -> str:
    amelia = db.execute(
        select(AgentDefinition).where(AgentDefinition.slug == AMELIA_SLUG)
    ).scalar_one_or_none()
    if amelia and str(amelia.telnyx_assistant_id or "").strip():
        return str(amelia.telnyx_assistant_id).strip()
    return os.environ.get("SURVEY_TELNYX_ASSISTANT_ID", "").strip()


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        telnyx_id = _resolve_telnyx_assistant_id(db)

        agent = db.execute(
            select(AgentDefinition).where(AgentDefinition.slug == SALES_AGENT_SLUG)
        ).scalar_one_or_none()
        if agent is None:
            agent = AgentDefinition(
                name=SALES_AGENT_NAME,
                slug=SALES_AGENT_SLUG,
                created_at=now,
            )
            db.add(agent)

        agent.name = SALES_AGENT_NAME
        agent.description = "Sales demo: warm 3-question phone survey (copy of Amelia)"
        agent.system_prompt = SYSTEM_PROMPT
        agent.call_workflow = CALL_WORKFLOW
        agent.voice_label = "Joe"
        agent.voice_type_label = "British English · warm"
        if telnyx_id:
            agent.telnyx_assistant_id = telnyx_id
        agent.base_role = BASE_ROLE
        agent.service_survey_role = SERVICE_SURVEY_ROLE
        agent.service_interview_role = None
        agent.opening_disclosure_template = OPENING_DISCLOSURE
        agent.supports_survey = True
        agent.supports_interview = False
        agent.supports_lead_sales = False
        agent.is_default_survey = False
        agent.is_default_interview = False
        agent.disclosure_for_survey = True
        agent.disclosure_for_interview = False
        agent.disclosure_mandatory = True
        agent.retry_policy_notes = "Demo agent — do not retry on no answer."
        agent.voicemail_behavior = "hang_up"
        agent.opt_out_policy_notes = "If asked to stop, acknowledge warmly, end the call, never retry."
        agent.is_active = True
        agent.updated_at = now
        db.commit()
        db.refresh(agent)
        print(f"OK: sales survey agent {agent.id} slug={agent.slug} telnyx={agent.telnyx_assistant_id or '(unset)'}")
        if not telnyx_id:
            print("WARN: no Telnyx assistant id resolved — set SURVEY_TELNYX_ASSISTANT_ID or seed Amelia first, then assign in Admin -> Agents.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
