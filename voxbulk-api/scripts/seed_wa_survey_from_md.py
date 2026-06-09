#!/usr/bin/env python3
"""Seed WA Survey survey types + Meta-ready abc_choice templates from a Markdown file.

Each block in the MD file becomes one survey type under the chosen industry:

  Morale
  📈 How would you describe the current mood and spirit within our team?
  A) Low B) Moderate C) High

Optional file header (YAML frontmatter or plain lines):

  ---
  industry: Employee Survey
  industry_slug: employee_survey
  ---

If industry is omitted, the MD filename is used (employee-survey.md → employee_survey).

Usage:
  cd voxbulk-api
  source .venv/bin/activate
  python scripts/seed_wa_survey_from_md.py --dry-run seed-data/wa-survey/employee-experience.md
  python scripts/seed_wa_survey_from_md.py --industry-slug employee_survey seed-data/wa-survey/employee-experience.md
  python scripts/seed_wa_survey_from_md.py --overwrite seed-data/wa-survey/employee-experience.md

VPS:
  cd /www/voxbulk/voxbulk-api && bash scripts/seed_wa_survey_from_md.sh seed-data/wa-survey/employee-experience.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_md_seed_service import SurveyWaMdSeedError, SurveyWaMdSeedService


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Seed WA Survey types/templates from Markdown")
    parser.add_argument("md_file", help="Path to Markdown file with survey question blocks")
    parser.add_argument("--industry-name", default="", help="Industry display name (overrides MD header/filename)")
    parser.add_argument("--industry-slug", default="", help="Industry slug, e.g. employee_survey")
    parser.add_argument("--create-industry", action="store_true", help="Create industry if missing")
    parser.add_argument(
        "--no-create-types",
        action="store_true",
        help="Require survey types to already exist under the industry (default: create missing types)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing abc_choice templates")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview only — no DB writes")
    parser.add_argument("--language", default="en_GB", help="WhatsApp template language (default en_GB)")
    args = parser.parse_args()

    md_path = Path(args.md_file)
    if not md_path.is_file() and (ROOT / md_path).is_file():
        md_path = ROOT / md_path

    try:
        with get_sessionmaker()() as db:
            result = SurveyWaMdSeedService.seed_from_markdown_file(
                db,
                md_path=md_path,
                industry_slug=args.industry_slug.strip() or None,
                industry_name=args.industry_name.strip() or None,
                create_industry=bool(args.create_industry),
                create_missing_types=not bool(args.no_create_types),
                overwrite_templates=bool(args.overwrite),
                dry_run=bool(args.dry_run),
                language=args.language.strip() or "en_GB",
            )
    except SurveyWaMdSeedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  WA SURVEY MD SEED")
    print("=" * 60)
    print(f"  File:      {result.get('md_file')}")
    print(f"  Industry:  {result.get('industry_name')} ({result.get('industry_slug')})")
    print(f"  Questions: {result.get('question_count')}")
    if result.get("dry_run"):
        print("  Mode:      dry-run (no database changes)")
        for row in result.get("preview") or []:
            print(f"\n  • {row.get('survey_type')}")
            print(f"    body: {row.get('body')}")
            print(f"    wizard: {row.get('wizard_description')}")
            print(f"    buttons: {' / '.join(row.get('buttons') or [])}")
        print("\nDone — re-run without --dry-run to write to the database.")
        return 0

    print(f"  Types +created: {result.get('survey_types_created')}")
    print(f"  Types existing: {result.get('survey_types_existing')}")
    print(f"  Templates +created: {result.get('templates_created')}")
    print(f"  Templates updated: {result.get('templates_updated')}")
    print(f"  Templates skipped: {result.get('templates_skipped')}")
    print("")
    for row in result.get("rows") or []:
        print(
            f"  [{row.get('action')}] {row.get('survey_type_name')} "
            f"→ template #{row.get('template_id')} ({', '.join(row.get('buttons') or [])})"
        )
    print("\nDone — sync templates to Telnyx from Admin when ready.")
    if args.dry_run:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
