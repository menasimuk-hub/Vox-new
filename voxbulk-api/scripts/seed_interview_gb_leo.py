#!/usr/bin/env python3
"""Seed or update the default GB interview voice agent (interview_GB-Leo).

Usage (from voxbulk-api, project venv — NOT system python):
  source .venv/bin/activate
  python scripts/seed_interview_gb_leo.py

Or:
  .venv/bin/python scripts/seed_interview_gb_leo.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _require_sqlalchemy2() -> None:
    try:
        import sqlalchemy
        from sqlalchemy.orm import DeclarativeBase  # noqa: F401
    except ImportError:
        print(
            "ERROR: SQLAlchemy 2.x required. Do not use system python (/usr/bin/python3).\n"
            "Run:\n"
            "  cd voxbulk-api\n"
            "  source .venv/bin/activate\n"
            "  python scripts/seed_interview_gb_leo.py\n"
            "Or:\n"
            "  .venv/bin/python scripts/seed_interview_gb_leo.py",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    parts = str(getattr(sqlalchemy, "__version__", "0")).split(".")
    try:
        major = int(parts[0])
    except ValueError:
        major = 0
    if major < 2:
        print(
            f"ERROR: Found SQLAlchemy {sqlalchemy.__version__} — need 2.x from voxbulk-api/.venv.\n"
            "Run: .venv/bin/python scripts/seed_interview_gb_leo.py",
            file=sys.stderr,
        )
        raise SystemExit(1)


_require_sqlalchemy2()

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.survey_voice_agent_service import _clear_other_defaults

SLUG = "interview-gb-leo"
TELNYX_ID = "assistant-19b10379-bea4-4a0e-ad82-c220d0fd54fd"
KB_PATH = ROOT / "kb-upload-ready" / "interview" / "interview_GB-Leo-kb.md"

SYSTEM_PROMPT = """You are Leo, a professional British English AI phone interviewer for {company_name}.
You conduct job screening interviews on behalf of {organiser_name} — never describe this as a survey.
Follow the approved interview script: OPENING DISCLOSURE is already spoken; continue with INTRO, then questions.
Ask the first two questions from the candidate CV, then questions from the role criteria.
One question at a time. Be warm, concise, and fair. Never promise an offer."""

BASE_ROLE = """British English. Professional and approachable. Pause after each question.
Use brief follow-ups only when needed. Respect interruptions and repeat the current step clearly."""

INTERVIEW_ROLE = """Conduct structured phone screening interviews.
Questions 1–2: reference the candidate CV (experience, achievement, or gap).
Questions 3+: from the job role and screening criteria supplied for this campaign.
Score answers mentally for clarity, relevance, and evidence. Never say 'survey'."""

CALL_WORKFLOW = """After disclosure: confirm candidate name and role → ask if they have 10–15 minutes now.
If yes: proceed with CV questions then role questions in order.
If no: offer a callback during working hours and end politely.
Close with thanks and next-steps from the hiring team."""

OPENING_DISCLOSURE = (
    "Hello {first_name}, this is {agent_name} calling on behalf of {company_name} "
    "about the {role} role. This call is recorded for quality and assessment. Is now a good time to speak?"
)


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == SLUG)).scalar_one_or_none()
        now = datetime.utcnow()
        if agent is None:
            agent = AgentDefinition(
                name="interview_GB-Leo",
                slug=SLUG,
                description="Default GB English AI phone interviewer — CV + role screening",
                system_prompt=SYSTEM_PROMPT,
                call_workflow=CALL_WORKFLOW,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(agent)
        else:
            agent.updated_at = now

        agent.name = "interview_GB-Leo"
        agent.description = "Default GB English AI phone interviewer — CV + role screening"
        agent.system_prompt = SYSTEM_PROMPT
        agent.call_workflow = CALL_WORKFLOW
        agent.voice_label = "Leo"
        agent.voice_type_label = "British English"
        agent.telnyx_assistant_id = TELNYX_ID
        agent.base_role = BASE_ROLE
        agent.service_interview_role = INTERVIEW_ROLE
        agent.opening_disclosure_template = OPENING_DISCLOSURE
        agent.supports_survey = False
        agent.supports_interview = True
        agent.supports_lead_sales = False
        agent.is_default_interview = True
        agent.is_default_survey = False
        agent.disclosure_for_interview = True
        agent.disclosure_for_survey = False
        agent.disclosure_mandatory = True
        agent.retry_policy_notes = "Retry once after 2 hours for busy or no answer."
        agent.interruption_behavior_notes = "If interrupted before finishing a question, pause and repeat it clearly."
        agent.voicemail_behavior = "leave_message"
        agent.opt_out_policy_notes = "If remove me or stop calling, acknowledge, end call, never retry."
        agent.is_active = True

        if KB_PATH.is_file():
            agent.kb_context = KB_PATH.read_text(encoding="utf-8")[:20000]

        _clear_other_defaults(db, agent, "is_default_interview")
        db.commit()
        db.refresh(agent)

        print(f"OK: interview agent {agent.id} slug={SLUG} telnyx={TELNYX_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
