#!/usr/bin/env python3
"""Remove mistaken survey_type_templates links (templates synced onto wrong survey types).

Usage:
  cd voxbulk-api
  python scripts/cleanup_wa_survey_template_links.py --dry-run
  python scripts/cleanup_wa_survey_template_links.py
  python scripts/cleanup_wa_survey_template_links.py --survey-type-slug customer_satisfaction
"""

from __future__ import annotations

import argparse
import sys

from app.core.database import get_sessionmaker
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean mistaken WA survey template links")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not delete")
    parser.add_argument("--survey-type-slug", default="", help="Limit cleanup to one survey type slug")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        SurveyTypeService.ensure_defaults(db)
        survey_type_id = None
        if args.survey_type_slug.strip():
            row = SurveyTypeService.get_by_slug(db, args.survey_type_slug.strip())
            if row is None:
                print(f"Survey type not found: {args.survey_type_slug}", file=sys.stderr)
                return 1
            survey_type_id = row.id
            print(f"Scoped to survey type: {row.name} ({row.slug})")

        result = SurveyTypeTemplateService.cleanup_mistaken_links(
            db,
            survey_type_id=survey_type_id,
            dry_run=bool(args.dry_run),
        )
        mode = "DRY RUN" if result["dry_run"] else "APPLIED"
        print(f"[{mode}] scanned={result['scanned']} removed={result['removed']} mistaken links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
