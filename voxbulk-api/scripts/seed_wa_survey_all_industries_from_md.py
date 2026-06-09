#!/usr/bin/env python3
"""Seed all WA Survey industries + abc_choice templates from the master Markdown catalog.

Ensures industries/survey types exist, then overwrites local abc_choice template drafts
with the canonical question bodies and A/B/C buttons. Sync to Telnyx manually from Admin.

Usage:
  cd voxbulk-api
  python scripts/seed_wa_survey_all_industries_from_md.py --dry-run
  python scripts/seed_wa_survey_all_industries_from_md.py
  python scripts/seed_wa_survey_all_industries_from_md.py --rebuild-md

VPS:
  cd /www/voxbulk/voxbulk-api && bash scripts/seed_wa_survey_all_industries_from_md.sh
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_wa_md_seed_service import SurveyWaMdSeedError, SurveyWaMdSeedService

DEFAULT_MD = ROOT / "seed-data" / "wa-survey" / "all-industries-abc-templates.md"
BUILD_SCRIPT = ROOT / "scripts" / "build_wa_survey_master_md.py"


def _rebuild_master_md() -> None:
    subprocess.run([sys.executable, str(BUILD_SCRIPT)], check=True, cwd=str(ROOT))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Seed all WA Survey industry abc_choice templates from master Markdown"
    )
    parser.add_argument(
        "--md-file",
        default=str(DEFAULT_MD),
        help=f"Master Markdown path (default: {DEFAULT_MD.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--rebuild-md",
        action="store_true",
        help="Regenerate master Markdown from seed_data/wa_survey_abc_catalog.py first",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview only — no DB writes")
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip templates that already exist (default: overwrite all abc_choice drafts)",
    )
    parser.add_argument("--language", default="en_GB", help="WhatsApp template language (default en_GB)")
    args = parser.parse_args()

    if args.rebuild_md:
        print("Rebuilding master Markdown from catalog…")
        _rebuild_master_md()

    md_path = Path(args.md_file)
    if not md_path.is_file() and (ROOT / md_path).is_file():
        md_path = ROOT / md_path
    if not md_path.is_file() and args.rebuild_md is False and BUILD_SCRIPT.is_file():
        print("Master Markdown missing — building from catalog…")
        _rebuild_master_md()

    try:
        with get_sessionmaker()() as db:
            if not args.dry_run:
                catalog = SurveyIndustrySeedService.ensure_catalog(db)
                print(
                    f"Industries ready — created {catalog.get('industries_created', 0)}, "
                    f"existing {catalog.get('industries_existing', 0)}; "
                    f"survey types +{catalog.get('survey_types_created', 0)}."
                )

            result = SurveyWaMdSeedService.seed_all_industries_from_markdown_file(
                db,
                md_path=md_path,
                create_missing_types=True,
                overwrite_templates=not bool(args.no_overwrite),
                dry_run=bool(args.dry_run),
                language=args.language.strip() or "en_GB",
            )
    except SurveyWaMdSeedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: failed to rebuild master Markdown: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  WA SURVEY — ALL INDUSTRIES MD SEED")
    print("=" * 60)
    print(f"  File:       {result.get('md_file')}")
    print(f"  Industries: {result.get('industry_count')}")
    print(f"  Questions:  {result.get('question_count')}")

    if result.get("dry_run"):
        print("  Mode:       dry-run (no database changes)")
        if result.get("preview_truncated"):
            print("  Preview:    first 40 questions only")
        for row in result.get("preview") or []:
            print(
                f"\n  • [{row.get('industry')}] {row.get('survey_type')}\n"
                f"    {row.get('body')}\n"
                f"    buttons: {' / '.join(row.get('buttons') or [])}"
            )
        print("\nDone — re-run without --dry-run to write to the database.")
        return 0

    print(f"  Templates +created: {result.get('templates_created')}")
    print(f"  Templates updated:  {result.get('templates_updated')}")
    print(f"  Templates skipped:  {result.get('templates_skipped')}")
    print("")
    for industry in result.get("industries") or []:
        print(
            f"  {industry.get('industry_name')} ({industry.get('industry_slug')}): "
            f"{industry.get('question_count')} questions — "
            f"+{industry.get('templates_created')} created, "
            f"{industry.get('templates_updated')} updated, "
            f"{industry.get('templates_skipped')} skipped"
        )
    print("\nDone — open Admin → WA Survey and sync templates to Telnyx when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
