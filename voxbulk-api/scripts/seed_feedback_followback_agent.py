#!/usr/bin/env python3
"""Seed or update the GB Customer Feedback AI follow-back voice agent.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_feedback_followback_agent.py

Set FEEDBACK_FOLLOWBACK_TELNYX_ASSISTANT_ID in env before running on production
(or it falls back to SURVEY_TELNYX_ASSISTANT_ID).
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

DEFAULT_TELNYX = (
    os.environ.get("FEEDBACK_FOLLOWBACK_TELNYX_ASSISTANT_ID", "").strip()
    or os.environ.get("SURVEY_TELNYX_ASSISTANT_ID", "").strip()
)

SLUG = "feedback-followback-gb"

SYSTEM_PROMPT = """You are {agent_name}, a British English AI phone agent for {company_name}.
This is a service-recovery follow-up after customer feedback — not a survey script and not a sales call.
The opening disclosure (including recording notice) is already spoken; continue warmly and listen first.
Ask one open question about what went wrong, summarise back, thank them, and close within three minutes."""

BASE_ROLE = """British English. Calm, empathetic, never defensive. Listen more than you talk.
Respect opt-out immediately. Never argue or blame staff by name."""

CALL_WORKFLOW = """Confirm they have a minute → one gentle open question on the lowest-rated topic →
summarise what you heard → thank them → close. If busy or upset, apologise and offer human callback."""

SERVICE_ROLE = (
    "Service-recovery follow-up caller for unhappy Customer Feedback respondents. "
    "Soft opener, one open question, under three minutes, recording disclosure mandatory."
)

OPENING_DISCLOSURE = (
    "Hello, this is {agent_name} calling from {company_name} about your recent feedback. "
    "This call is recorded for quality. Do you have a minute so we can understand how to do better?"
)


def _upsert_agent(db, *, now: datetime) -> AgentDefinition:
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == SLUG)).scalar_one_or_none()
    if agent is None:
        agent = AgentDefinition(
            name="AI Follow-back Assistant",
            slug=SLUG,
            description="GB English AI follow-back agent for Customer Feedback recovery calls",
            system_prompt=SYSTEM_PROMPT,
            call_workflow=CALL_WORKFLOW,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
    else:
        agent.updated_at = now

    agent.name = "AI Follow-back Assistant"
    agent.description = "GB English AI follow-back agent for Customer Feedback recovery calls"
    agent.system_prompt = SYSTEM_PROMPT
    agent.call_workflow = CALL_WORKFLOW
    agent.voice_label = "Follow-back"
    agent.voice_type_label = "British English · empathetic recovery"
    if DEFAULT_TELNYX:
        agent.telnyx_assistant_id = DEFAULT_TELNYX
    agent.base_role = BASE_ROLE
    agent.service_survey_role = SERVICE_ROLE
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
    agent.retry_policy_notes = "No automatic retry in v1 — one attempt per session."
    agent.interruption_behavior_notes = (
        "If interrupted during the opening disclosure, repeat the full disclosure verbatim including "
        "that the call is recorded."
    )
    agent.voicemail_behavior = "hang_up"
    agent.opt_out_policy_notes = "If remove me or stop calling, acknowledge, end call, never retry."
    agent.is_active = True
    return agent


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        agent = _upsert_agent(db, now=now)
        db.commit()
        db.refresh(agent)
        print(f"OK: follow-back agent {agent.id} slug={agent.slug} telnyx={agent.telnyx_assistant_id or '(unset)'}")
        if not DEFAULT_TELNYX:
            print(
                "WARN: FEEDBACK_FOLLOWBACK_TELNYX_ASSISTANT_ID / SURVEY_TELNYX_ASSISTANT_ID not set — "
                "assign a Telnyx assistant ID in Admin before production calls."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
