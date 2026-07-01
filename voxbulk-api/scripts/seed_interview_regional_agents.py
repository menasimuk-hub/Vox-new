#!/usr/bin/env python3
"""Seed or update all English regional interview voice agents (12 agents).

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_interview_regional_agents.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.interview_agent_regions import INTERVIEW_ENGLISH_ROSTER, INTERVIEW_REGIONS
from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.survey_voice_agent_service import _clear_other_defaults

KB_DIR = ROOT / "kb-upload-ready" / "interview"
DEFAULT_TELNYX_GB_LEO = "assistant-6b6dbef2-8a40-442d-9e7a-9b11eaa7d9ed"


def _load_kb(accent_region: str) -> str:
    base = KB_DIR / "interview-conduct-base.md"
    accent = KB_DIR / f"interview-region-accent-{accent_region}.md"
    parts: list[str] = []
    if base.is_file():
        parts.append(base.read_text(encoding="utf-8"))
    if accent.is_file():
        parts.append(accent.read_text(encoding="utf-8"))
    legacy = KB_DIR / "interview_GB-Leo-kb.md"
    if accent_region == "GB" and legacy.is_file():
        parts.append(legacy.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)[:20000]


def _prompts(spec) -> dict[str, str]:
    region = INTERVIEW_REGIONS[spec.accent_region]
    agent_name = spec.voice_label
    accent_line = region.english_label
    gender_tone = "warm and professional" if spec.gender == "female" else "confident and approachable"

    system_prompt = f"""You are {agent_name}, a professional {accent_line} AI phone interviewer for {{company_name}}.
You conduct job screening interviews on behalf of {{organiser_name}} — never describe this as a survey.
Follow the approved interview script: OPENING DISCLOSURE is already spoken; continue with INTRO, then questions.
Ask the first two questions from the candidate CV, then questions from the role criteria.
One question at a time. Be {gender_tone}. Never promise an offer."""

    base_role = f"""{accent_line}. {gender_tone.capitalize()}. Pause after each question.
Use brief follow-ups only when needed. Respect interruptions and repeat the current step clearly."""

    interview_role = """Conduct structured phone screening interviews.
Questions 1–2: reference the candidate CV (experience, achievement, or gap).
Questions 3+: from the job role and screening criteria supplied for this campaign.
Score answers mentally for clarity, relevance, and evidence. Never say 'survey'."""

    call_workflow = """After disclosure: confirm candidate name and role → ask if they have 10–15 minutes now.
If yes: proceed with CV questions then role questions in order.
If no: offer a callback during working hours and end politely.
Close with thanks and next-steps from the hiring team."""

    opening = (
        f"Hello {{first_name}}, this is {agent_name} calling on behalf of {{company_name}} "
        f"about the {{role}} role. This call is recorded for quality and assessment. Is now a good time to speak?"
    )

    return {
        "system_prompt": system_prompt,
        "base_role": base_role,
        "service_interview_role": interview_role,
        "call_workflow": call_workflow,
        "opening_disclosure_template": opening,
    }


def _resolve_telnyx_id(spec) -> str | None:
    import os

    key = spec.telnyx_env_key
    if key:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    if spec.slug == "interview-gb-leo":
        legacy = os.environ.get("INTERVIEW_TELNYX_ASSISTANT_ID", "").strip()
        return legacy or DEFAULT_TELNYX_GB_LEO
    return None


def upsert_agent(db, spec, *, now: datetime) -> AgentDefinition:
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec.slug)).scalar_one_or_none()
    prompts = _prompts(spec)
    kb_text = _load_kb(spec.accent_region)

    if agent is None:
        agent = AgentDefinition(
            name=spec.name,
            slug=spec.slug,
            description=f"{INTERVIEW_REGIONS[spec.accent_region].label} English AI phone interviewer",
            system_prompt=prompts["system_prompt"],
            call_workflow=prompts["call_workflow"],
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
    else:
        agent.updated_at = now

    agent.name = spec.name
    agent.description = f"{INTERVIEW_REGIONS[spec.accent_region].label} English AI phone interviewer"
    agent.system_prompt = prompts["system_prompt"]
    agent.call_workflow = prompts["call_workflow"]
    agent.voice_label = spec.voice_label
    agent.voice_type_label = spec.voice_type_label
    agent.accent_region = spec.accent_region
    agent.gender = spec.gender
    telnyx_id = _resolve_telnyx_id(spec)
    if telnyx_id and not str(agent.telnyx_assistant_id or "").strip():
        agent.telnyx_assistant_id = telnyx_id
    agent.base_role = prompts["base_role"]
    agent.service_interview_role = prompts["service_interview_role"]
    agent.opening_disclosure_template = prompts["opening_disclosure_template"]
    agent.supports_survey = False
    agent.supports_interview = True
    agent.supports_lead_sales = False
    agent.is_default_interview = bool(spec.is_default_interview)
    agent.is_default_survey = False
    agent.disclosure_for_interview = True
    agent.disclosure_for_survey = False
    agent.disclosure_mandatory = True
    agent.retry_policy_notes = "Retry once after 2 hours for busy or no answer."
    agent.interruption_behavior_notes = "If interrupted before finishing a question, pause and repeat it clearly."
    agent.voicemail_behavior = "leave_message"
    agent.opt_out_policy_notes = "If remove me or stop calling, acknowledge, end call, never retry."
    agent.is_active = True
    if kb_text:
        agent.kb_context = kb_text

    if spec.is_default_interview:
        _clear_other_defaults(db, agent, "is_default_interview")

    return agent


def main() -> int:
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        for spec in INTERVIEW_ENGLISH_ROSTER:
            row = upsert_agent(db, spec, now=now)
            db.flush()
            print(f"OK: {row.slug} id={row.id} region={row.accent_region} gender={row.gender} telnyx={row.telnyx_assistant_id or '(unset)'}")
        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
