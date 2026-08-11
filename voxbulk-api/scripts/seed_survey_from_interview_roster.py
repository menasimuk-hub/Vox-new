#!/usr/bin/env python3
"""Create missing AI Call Survey agents by cloning interview personas.

Idempotent: if a survey-* agent already exists for the same accent_region + gender
(or GB slots Amelia/James), skip — do not overwrite.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_survey_from_interview_roster.py
  .venv/bin/python scripts/seed_survey_from_interview_roster.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.interview_agent_regions import INTERVIEW_REGIONS
from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition

KB_PATH = ROOT / "kb-upload-ready" / "survey" / "survey-conduct-gb.md"

CALL_WORKFLOW = """After disclosure: confirm availability → ask survey questions in order (max four) → thank and close.
If unavailable, end politely. Never sell or interview."""

SERVICE_SURVEY_ROLE = (
    "Experienced phone survey caller for businesses. "
    "Friendly, concise, maximum four survey questions per call."
)


def _agent_gender(agent: AgentDefinition) -> str:
    g = str(getattr(agent, "gender", None) or "").strip().lower()
    if g in {"male", "female"}:
        return g
    blob = f"{agent.slug} {agent.name} {agent.voice_label}".lower()
    if any(x in blob for x in ("amelia", "jode", "fiona", "maya", "elena", "chloe", "niamh", "female")):
        return "female"
    if any(x in blob for x in ("james", "leo", "jack", "liam", "marcus", "callum", "sean", "jammal", "sultan", "male")):
        return "male"
    return "unknown"


def _agent_region(agent: AgentDefinition) -> str:
    ar = str(getattr(agent, "accent_region", None) or "").strip().upper()
    if ar:
        return ar
    slug = str(agent.slug or "")
    m = re.search(r"(?:interview|survey|ai-demo-interview)-([a-z]{2})-", slug, re.I)
    if m:
        return m.group(1).upper()
    if "sultan" in slug:
        return "SA"
    if "jammal" in slug:
        return "EG"
    return "GB"


def _survey_slug(region: str, voice_label: str) -> str:
    voice = re.sub(r"[^a-z0-9]+", "", str(voice_label or "agent").strip().lower()) or "agent"
    return f"survey-{region.lower()}-{voice}"


def _region_english_label(region: str) -> str:
    if region in INTERVIEW_REGIONS:
        return INTERVIEW_REGIONS[region].english_label
    if region == "SA":
        return "Saudi Gulf Arabic"
    if region == "EG":
        return "Egyptian Arabic"
    return "English"


def _survey_prompts(*, voice_label: str, region: str, gender: str) -> dict[str, str]:
    accent = _region_english_label(region)
    gender_tone = "warm and professional" if gender == "female" else "confident and approachable"
    system_prompt = f"""You are {voice_label}, a {accent} AI phone survey caller for {{company_name}}.
Conduct a short customer survey — never describe this as a job interview.
Follow the approved survey script: OPENING DISCLOSURE is already spoken; continue with INTRO, then questions.
Ask at most four survey questions in order. One question at a time. Be {gender_tone} and concise."""
    base_role = f"""{accent}. {gender_tone.capitalize()}. Pause after each question.
Accept brief answers. Respect opt-out immediately."""
    opening = (
        f"Hello {{first_name}}, this is {voice_label} calling on behalf of {{company_name}} "
        "for a short customer survey. This call is recorded for quality. "
        "Do you have two or three minutes now?"
    )
    voice_type = f"{accent} · {'female' if gender == 'female' else 'male'}"
    return {
        "system_prompt": system_prompt,
        "base_role": base_role,
        "opening_disclosure_template": opening,
        "voice_type_label": voice_type,
    }


def _list_interview_sources(db) -> list[AgentDefinition]:
    rows = list(
        db.execute(
            select(AgentDefinition)
            .where(
                AgentDefinition.is_active.is_(True),
                AgentDefinition.supports_interview.is_(True),
            )
            .order_by(AgentDefinition.slug.asc())
        ).scalars()
    )
    return [a for a in rows if not bool(getattr(a, "supports_ai_demo", False))]


def _list_survey_agents(db) -> list[AgentDefinition]:
    return list(
        db.execute(
            select(AgentDefinition)
            .where(
                AgentDefinition.is_active.is_(True),
                AgentDefinition.supports_survey.is_(True),
                AgentDefinition.slug.like("survey-%"),
            )
            .order_by(AgentDefinition.slug.asc())
        ).scalars()
    )


def _survey_slot_map(survey_agents: list[AgentDefinition]) -> dict[tuple[str, str], AgentDefinition]:
    out: dict[tuple[str, str], AgentDefinition] = {}
    for a in survey_agents:
        key = (_agent_region(a), _agent_gender(a))
        if key[1] == "unknown":
            continue
        out.setdefault(key, a)
    return out


def _create_survey_from_interview(
    db,
    source: AgentDefinition,
    *,
    region: str,
    gender: str,
    kb_text: str,
    now: datetime,
    dry_run: bool,
) -> AgentDefinition | None:
    voice = str(source.voice_label or source.name or "Agent").strip()
    slug = _survey_slug(region, voice)
    existing = db.execute(select(AgentDefinition).where(AgentDefinition.slug == slug)).scalar_one_or_none()
    if existing is not None:
        print(f"  SKIP slug-exists {slug}")
        return existing

    prompts = _survey_prompts(voice_label=voice, region=region, gender=gender)
    name = f"survey_{region}-{voice}"
    print(f"  CREATE {slug} from {source.slug} ({region}/{gender}) voice={voice}")
    if dry_run:
        return None

    agent = AgentDefinition(
        name=name,
        slug=slug,
        description=f"{_region_english_label(region)} AI phone survey agent",
        system_prompt=prompts["system_prompt"],
        call_workflow=CALL_WORKFLOW,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    agent.voice_label = voice
    agent.voice_type_label = prompts["voice_type_label"]
    agent.accent_region = region
    agent.gender = gender
    agent.base_role = prompts["base_role"]
    agent.service_survey_role = SERVICE_SURVEY_ROLE
    agent.service_interview_role = None
    agent.opening_disclosure_template = prompts["opening_disclosure_template"]
    agent.supports_survey = True
    agent.supports_interview = False
    agent.supports_lead_sales = False
    agent.supports_appointment = False
    agent.supports_ai_demo = False
    agent.is_default_survey = False
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
    if kb_text:
        agent.kb_context = kb_text[:20000]
    # Do not copy interview Telnyx ID — provision script creates a survey assistant.
    db.add(agent)
    return agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed missing survey agents from interview roster")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    kb_text = KB_PATH.read_text(encoding="utf-8") if KB_PATH.is_file() else ""
    Session = get_sessionmaker()
    db = Session()
    created = 0
    skipped = 0
    try:
        interview = _list_interview_sources(db)
        survey = _list_survey_agents(db)
        slots = _survey_slot_map(survey)
        print(f"Interview sources: {len(interview)}")
        print(f"Survey existing:   {len(survey)}")
        now = datetime.utcnow()

        for source in interview:
            region = _agent_region(source)
            gender = _agent_gender(source)
            if region == "SA" and gender == "unknown":
                gender = "male"
            if gender not in {"male", "female"}:
                print(f"  SKIP unknown-gender {source.slug}")
                skipped += 1
                continue
            key = (region, gender)
            existing = slots.get(key)
            if existing is not None:
                print(f"  SKIP slot {key} interview={source.slug} survey={existing.slug}/{existing.voice_label}")
                skipped += 1
                continue
            row = _create_survey_from_interview(
                db,
                source,
                region=region,
                gender=gender,
                kb_text=kb_text,
                now=now,
                dry_run=args.dry_run,
            )
            if row is not None and not args.dry_run:
                slots[key] = row
                created += 1
            elif args.dry_run:
                created += 1

        if not args.dry_run:
            db.commit()
        print(f"\nDone. skipped={skipped} created={created} dry_run={args.dry_run}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
