#!/usr/bin/env python3
"""Create Telnyx assistants for survey-* agents that have no assistant ID yet.

Skips rows that already have telnyx_assistant_id. Templates voice/model from Amelia
when possible; otherwise from the matching interview agent for the same region/gender.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_survey_from_interview_roster.py
  .venv/bin/python scripts/provision_survey_telnyx_assistants.py --dry-run
  .venv/bin/python scripts/provision_survey_telnyx_assistants.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.telnyx_assistant_service import (
    build_agent_greeting,
    create_telnyx_assistant,
    normalize_telnyx_assistant_id,
    template_assistant_create_defaults,
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


def _telnyx_name(agent: AgentDefinition) -> str:
    region = _agent_region(agent)
    voice = str(agent.voice_label or agent.name or "Agent").strip()
    g = "F" if _agent_gender(agent) == "female" else "M"
    return f"VOXBULK Survey {region} {voice} {g}"


def _instructions(agent: AgentDefinition) -> str:
    voice = str(agent.voice_label or "the survey agent").strip()
    return (
        f"You are {voice}, an AI phone survey caller for {{company_name}}. "
        "Conduct a short customer survey — never describe this as a job interview. "
        "Ask at most four survey questions in order, one at a time. Be warm and concise."
    )


def _resolve_amelia_template_id(db) -> str:
    row = db.execute(
        select(AgentDefinition).where(AgentDefinition.slug == "survey-gb-amelia")
    ).scalar_one_or_none()
    if row and str(row.telnyx_assistant_id or "").strip():
        return str(row.telnyx_assistant_id).strip()
    return ""


def _matching_interview_template_id(db, survey: AgentDefinition) -> str:
    region = _agent_region(survey)
    gender = _agent_gender(survey)
    rows = list(
        db.execute(
            select(AgentDefinition).where(
                AgentDefinition.is_active.is_(True),
                AgentDefinition.supports_interview.is_(True),
                AgentDefinition.supports_ai_demo.is_(False),
            )
        ).scalars()
    )
    for row in rows:
        if _agent_region(row) == region and _agent_gender(row) == gender:
            tid = str(row.telnyx_assistant_id or "").strip()
            if tid:
                return tid
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Telnyx assistants for survey agents")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    Session = get_sessionmaker()
    db = Session()
    errors = 0
    created = 0
    skipped = 0
    try:
        survey_agents = list(
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
        amelia_id = _resolve_amelia_template_id(db)
        amelia_defaults: dict = {}
        if amelia_id:
            try:
                amelia_defaults = template_assistant_create_defaults(db, amelia_id)
                print(f"Amelia template: {amelia_id} model={amelia_defaults.get('model')}")
            except Exception as exc:
                print(f"WARN: could not load Amelia template {amelia_id}: {exc}")

        for agent in survey_agents:
            existing = str(agent.telnyx_assistant_id or "").strip()
            if existing:
                print(f"  SKIP has-id {agent.slug} -> {existing}")
                skipped += 1
                continue

            interview_tid = _matching_interview_template_id(db, agent)
            template_id = interview_tid or amelia_id
            defaults = dict(amelia_defaults)
            if interview_tid and interview_tid != amelia_id:
                try:
                    defaults = template_assistant_create_defaults(db, interview_tid)
                except Exception as exc:
                    print(f"  WARN {agent.slug}: interview template {interview_tid}: {exc}")

            name = _telnyx_name(agent)
            instructions = _instructions(agent)
            greeting = build_agent_greeting(str(agent.voice_label or "there"))
            voice_settings = defaults.get("voice_settings")
            model = defaults.get("model")

            if args.dry_run:
                print(
                    f"  [create] {agent.slug} name={name} template={template_id or '(none)'} "
                    f"model={model} voice={voice_settings}"
                )
                created += 1
                continue

            if not template_id and not voice_settings:
                errors += 1
                print(f"  ERROR {agent.slug}: no template or voice settings — set Amelia Telnyx ID first")
                continue

            try:
                created_row = create_telnyx_assistant(
                    db,
                    name=name,
                    instructions=instructions,
                    model=model,
                    greeting=greeting,
                    voice_settings=voice_settings,
                )
                assistant_id = normalize_telnyx_assistant_id(str(created_row.get("id") or "").strip())
                if not assistant_id:
                    raise ValueError("Telnyx create returned empty id")
                agent.telnyx_assistant_id = assistant_id
                db.add(agent)
                print(f"  created {agent.slug} -> {assistant_id}")
                created += 1
            except Exception as exc:
                errors += 1
                print(f"  ERROR {agent.slug}: {exc}")

        if not args.dry_run:
            db.commit()
        print(f"\nDone. skipped={skipped} created={created} errors={errors} dry_run={args.dry_run}")
        return 1 if errors else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
