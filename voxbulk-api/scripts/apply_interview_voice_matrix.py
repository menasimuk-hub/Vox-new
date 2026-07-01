#!/usr/bin/env python3
"""Apply accent-appropriate voices to English interview Telnyx assistants.

Telnyx native voices first; ElevenLabs fallback where no Telnyx accent match.
Skips Arabic agents (interview-ar-*).

Usage (from voxbulk-api, project venv):
  python scripts/apply_interview_voice_matrix.py --discover
  python scripts/apply_interview_voice_matrix.py --dry-run
  python scripts/apply_interview_voice_matrix.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.interview_agent_regions import INTERVIEW_ENGLISH_ROSTER
from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.interview_voice_matrix_service import (
    REGION_ACCENT_KEYWORDS,
    apply_voice_to_assistant,
    discover_entry_for_spec,
    fetch_elevenlabs_voices,
    fetch_telnyx_voices,
    load_voice_matrix,
    matrix_entry_for_slug,
    voice_settings_from_entry,
)


def _print_entry(entry: dict, *, discovered: bool = False) -> None:
    slug = entry.get("slug")
    provider = entry.get("provider")
    voice = entry.get("voice")
    ref = entry.get("api_key_ref")
    print(f"  {slug}")
    print(f"    provider   {provider}")
    print(f"    voice      {voice}")
    if ref:
        print(f"    api_key_ref {ref}")
    fb = entry.get("fallback")
    if isinstance(fb, dict) and fb.get("voice"):
        print(f"    fallback   {fb.get('provider')}: {fb.get('voice')}")
    if discovered:
        meta = entry.get("_discover") or {}
        print(f"    scores     telnyx={meta.get('telnyx_score')} elevenlabs={meta.get('elevenlabs_score')}")


def cmd_discover(db) -> int:
    from app.services.interview_voice_matrix_service import MATRIX_PATH

    print(f"Discovering voices (matrix file: {MATRIX_PATH})")
    tx = fetch_telnyx_voices(db)
    el = fetch_elevenlabs_voices(db)
    print(f"  Telnyx voices listed: {len(tx)}")
    print(f"  ElevenLabs voices listed: {len(el)}")
    print("\nRecommended assignments (Telnyx-first):")
    for spec in INTERVIEW_ENGLISH_ROSTER:
        kw = list(REGION_ACCENT_KEYWORDS.get(spec.accent_region, []))  # noqa: F821
        entry = discover_entry_for_spec(
            db,
            slug=spec.slug,
            region=spec.accent_region,
            gender=spec.gender,
            accent_keywords=kw,
            telnyx_voices=tx,
            elevenlabs_voices=el,
        )
        _print_entry(entry, discovered=True)
    return 0


def cmd_apply(db, *, dry_run: bool) -> int:
    from app.services.interview_voice_matrix_service import MATRIX_PATH

    matrix = load_voice_matrix()
    if not matrix:
        print(f"No matrix at {MATRIX_PATH}")
        return 1

    errors = 0
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"{mode}: patching voice_settings on Telnyx assistants (English only)")
    for row in matrix:
        slug = str(row.get("slug") or "")
        if slug.startswith("interview-ar-"):
            print(f"  skip {slug} (Arabic — untouched)")
            continue
        agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == slug)).scalar_one_or_none()
        if agent is None:
            print(f"  skip {slug} — no DB agent row")
            continue
        assistant_id = str(agent.telnyx_assistant_id or "").strip()
        if not assistant_id:
            print(f"  skip {slug} — no telnyx_assistant_id in Admin/DB")
            continue
        try:
            settings = voice_settings_from_entry(row)
        except ValueError as exc:
            errors += 1
            print(f"  ERROR {slug}: {exc}")
            continue
        print(f"  {slug} -> {assistant_id}")
        print(f"    voice {settings.get('voice')}")
        if settings.get("api_key_ref"):
            print(f"    api_key_ref {settings.get('api_key_ref')}")
        try:
            apply_voice_to_assistant(db, assistant_id=assistant_id, voice_settings=settings, dry_run=dry_run)
            if not dry_run:
                print("    PATCH OK")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"    PATCH FAILED: {exc}")

    if errors:
        print(f"\n{errors} agent(s) failed")
        return 1
    print("\nDone. Test: python scripts/diagnose_interview_voice.py --agent Leo --preview")
    return 0


def cmd_dry_run(db) -> int:
    matrix = load_voice_matrix()
    print(f"Matrix entries: {len(matrix)}")
    for row in matrix:
        slug = str(row.get("slug") or "")
        entry = matrix_entry_for_slug(slug) or row
        agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == slug)).scalar_one_or_none()
        assistant_id = str(getattr(agent, "telnyx_assistant_id", None) or "") if agent else ""
        print(f"\n  {slug} assistant={assistant_id or '(unset)'}")
        _print_entry(entry)
        try:
            settings = voice_settings_from_entry(entry)
            print(f"    PATCH voice_settings={settings}")
        except ValueError as exc:
            print(f"    ERROR: {exc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply interview voice matrix to Telnyx assistants")
    parser.add_argument("--discover", action="store_true", help="Query Telnyx/ElevenLabs APIs and print recommendations")
    parser.add_argument("--dry-run", action="store_true", help="Show planned PATCH without calling Telnyx")
    parser.add_argument("--apply", action="store_true", help="PATCH voice_settings on each English assistant")
    args = parser.parse_args()

    if not args.discover and not args.dry_run and not args.apply:
        parser.error("provide --discover, --dry-run, or --apply")

    Session = get_sessionmaker()
    db = Session()
    try:
        if args.discover:
            return cmd_discover(db)
        if args.dry_run:
            return cmd_dry_run(db)
        return cmd_apply(db, dry_run=False)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
