#!/usr/bin/env python3
"""Bulk-generate normal WA Survey library templates (one per industry survey type).

Generates middle-step templates only (default step_role=rating). Does NOT generate
welcome, thank_you, tell_us_more, start, or completion templates — those belong to
Global System Templates.

Saved templates are LOCAL_DRAFT in the DB under the correct survey type. No Telnyx sync.

Usage:
  cd voxbulk-api
  source .venv/bin/activate   # VPS: required — plain python3 may miss dependencies
  python3 scripts/bulk_generate_wa_survey_library_templates.py --dry-run
  python3 scripts/bulk_generate_wa_survey_library_templates.py --limit 3
  python3 scripts/bulk_generate_wa_survey_library_templates.py --industry-slug hospitality_food
  python3 scripts/bulk_generate_wa_survey_library_templates.py --survey-type-slug food_quality
  python3 scripts/bulk_generate_wa_survey_library_templates.py --step-role yes_no --overwrite

  VPS one-liner (after git pull):
  cd /www/voxbulk/voxbulk-api && .venv/bin/python3 scripts/bulk_generate_wa_survey_library_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES
from app.services.survey_wa_bulk_library_template_service import (
    DEFAULT_LIBRARY_STEP_ROLE,
    SurveyWaBulkLibraryTemplateService,
)
from app.services.survey_wa_template_pack_service import SurveyWaTemplatePackError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-generate normal WA Survey templates (OpenAI → LOCAL_DRAFT, no Telnyx sync)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List actions without OpenAI or DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N industry/survey-type pairs")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing template for the step_role")
    parser.add_argument("--industry-slug", default="", help="Limit to one industry slug")
    parser.add_argument("--survey-type-slug", default="", help="Limit to one survey type slug")
    parser.add_argument(
        "--step-role",
        default=DEFAULT_LIBRARY_STEP_ROLE,
        choices=list(MIDDLE_STEP_ROLES),
        help=f"Middle step role to generate (default: {DEFAULT_LIBRARY_STEP_ROLE})",
    )
    parser.add_argument(
        "--instruction",
        default="",
        help="Optional extra admin instruction passed to OpenAI generation",
    )
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        SurveyIndustrySeedService.ensure_catalog(db)
        try:
            payload = SurveyWaBulkLibraryTemplateService.run_bulk(
                db,
                dry_run=bool(args.dry_run),
                limit=args.limit,
                overwrite=bool(args.overwrite),
                industry_slug=args.industry_slug.strip() or None,
                survey_type_slug=args.survey_type_slug.strip() or None,
                step_role=args.step_role,
                instruction=args.instruction.strip(),
            )
        except SurveyWaTemplatePackError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    summary = payload["summary"]
    print("=== WA Survey library bulk generation ===")
    print(
        f"step_role={summary['step_role']} dry_run={summary['dry_run_mode']} "
        f"overwrite={summary['overwrite_mode']} total={summary['total']}"
    )
    print(
        f"created={summary['created']} overwritten={summary['overwritten']} "
        f"skipped={summary['skipped']} failed={summary['failed']} dry_run={summary['dry_run']}"
    )
    print("")
    for result in payload["results"]:
        print(result.log_line())

    if summary["failed"]:
        return 1
    if summary["total"] == 0:
        print("\nNo matching industry/survey-type pairs found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
