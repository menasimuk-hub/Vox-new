#!/usr/bin/env python3
"""Create or sync Telnyx assistants for English regional interview agents.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_interview_regional_agents.py
  .venv/bin/python scripts/provision_interview_telnyx_assistants.py --dry-run
  .venv/bin/python scripts/provision_interview_telnyx_assistants.py

Run seed first so Leo's Telnyx ID is in the DB. New assistants clone model/voice
from Leo when INTERVIEW_VOICE_* env vars are not set.

Environment (optional):
  INTERVIEW_TELNYX_MODEL=openai/gpt-4o
  INTERVIEW_TELNYX_ASSISTANT_ID_GB_LEO=assistant-...
  INTERVIEW_VOICE_GB_MALE=ElevenLabs.eleven_flash_v2_5.{voice_id}
  INTERVIEW_VOICE_GB_FEMALE=...
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.interview_agent_regions import (
    INTERVIEW_ENGLISH_ROSTER,
    INTERVIEW_REGIONS,
    voice_env_key_for_region_gender,
)
from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.telnyx_assistant_service import (
    build_agent_greeting,
    create_telnyx_assistant,
    normalize_telnyx_assistant_id,
    sync_telnyx_assistant_instructions,
    template_assistant_create_defaults,
)

DEFAULT_LEO_TELNYX = "assistant-6b6dbef2-8a40-442d-9e7a-9b11eaa7d9ed"


def _voice_settings(spec) -> dict | None:
    key = voice_env_key_for_region_gender(spec.accent_region, spec.gender)
    slug_key = spec.telnyx_env_key.replace("INTERVIEW_TELNYX_ASSISTANT_ID", "INTERVIEW_VOICE")
    voice = os.environ.get(key, "").strip() or os.environ.get(slug_key, "").strip()
    if not voice:
        return None
    return {"voice": voice}


def _assistant_id_from_env(spec) -> str:
    return os.environ.get(spec.telnyx_env_key, "").strip()


def _resolve_template_id(db) -> str:
    for key in ("INTERVIEW_TELNYX_ASSISTANT_ID_GB_LEO", "INTERVIEW_TELNYX_ASSISTANT_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    row = db.execute(
        select(AgentDefinition).where(AgentDefinition.slug == "interview-gb-leo")
    ).scalar_one_or_none()
    if row and row.telnyx_assistant_id:
        return str(row.telnyx_assistant_id).strip()
    return DEFAULT_LEO_TELNYX


def _instructions(spec) -> str:
    region = INTERVIEW_REGIONS[spec.accent_region]
    gender_tone = "warm and professional" if spec.gender == "female" else "confident and approachable"
    return (
        f"You are {spec.voice_label}, a professional {region.english_label} AI phone interviewer for {{company_name}}. "
        f"Conduct job screening interviews on behalf of {{organiser_name}}. Never call this a survey. "
        f"Be {gender_tone}. One question at a time."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Telnyx interview assistants")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--region", help="Limit to accent region code (GB, US, …)")
    parser.add_argument("--create-missing", action="store_true", default=True)
    args = parser.parse_args()

    model_override = os.environ.get("INTERVIEW_TELNYX_MODEL", "").strip()
    region_filter = str(args.region or "").strip().upper()
    roster = [s for s in INTERVIEW_ENGLISH_ROSTER if not region_filter or s.accent_region == region_filter]

    Session = get_sessionmaker()
    db = Session()
    env_lines: list[str] = []
    errors = 0
    try:
        template_id = _resolve_template_id(db)
        template_defaults: dict = {}
        try:
            template_defaults = template_assistant_create_defaults(db, template_id)
            print(f"Template assistant: {template_id} model={template_defaults.get('model')}")
        except Exception as exc:
            print(f"WARN: could not load template assistant {template_id}: {exc}")

        for spec in roster:
            existing_id = _assistant_id_from_env(spec)
            row = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec.slug)).scalar_one_or_none()
            if not existing_id and row and row.telnyx_assistant_id:
                existing_id = str(row.telnyx_assistant_id).strip()
            if not existing_id and spec.slug == "interview-gb-leo":
                existing_id = template_id

            greeting = build_agent_greeting(spec.voice_label)
            instructions = _instructions(spec)
            voice_settings = _voice_settings(spec) or template_defaults.get("voice_settings")
            model = model_override or template_defaults.get("model")

            if args.dry_run:
                action = "sync" if existing_id else "create"
                print(
                    f"  [{action}] {spec.telnyx_name} env={spec.telnyx_env_key} "
                    f"model={model} voice={voice_settings}"
                )
                continue

            assistant_id = existing_id
            try:
                if not assistant_id and args.create_missing:
                    created = create_telnyx_assistant(
                        db,
                        name=spec.telnyx_name,
                        instructions=instructions,
                        model=model,
                        greeting=greeting,
                        voice_settings=voice_settings,
                    )
                    assistant_id = str(created.get("id") or "").strip()
                    print(f"  created {spec.slug} -> {assistant_id}")
                elif not assistant_id:
                    print(f"  skip {spec.slug} — no Telnyx ID (set {spec.telnyx_env_key})")
                    continue
                else:
                    sync_telnyx_assistant_instructions(
                        db,
                        assistant_id,
                        instructions,
                        greeting=greeting,
                        verify_live=False,
                    )
                    print(f"  synced {spec.slug} -> {assistant_id}")
            except Exception as exc:
                errors += 1
                print(f"  ERROR {spec.slug}: {exc}")
                continue

            if assistant_id:
                clean = normalize_telnyx_assistant_id(assistant_id)
                env_lines.append(f"{spec.telnyx_env_key}={clean}")
                if row:
                    row.telnyx_assistant_id = clean
                    db.add(row)
        if not args.dry_run:
            db.commit()
        if env_lines:
            print("\n# Add to voxbulk-api/.env:")
            for line in env_lines:
                print(line)
        if errors:
            print(f"\n{errors} assistant(s) failed — fix errors above and re-run.")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
