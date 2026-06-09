#!/usr/bin/env python3
"""Idempotent seed for WA Survey industries and service tags (survey types).

Safe to run multiple times on VPS — skips existing industries and survey types.

Usage:
  cd voxbulk-api
  python scripts/seed_wa_survey_industries.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_industry_seed_service import SurveyIndustrySeedService


def main() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        result = SurveyIndustrySeedService.ensure_catalog(db)

    print("=" * 60)
    print("  WA SURVEY INDUSTRY SEED COMPLETE")
    print("=" * 60)
    print(f"  Industries created:    {result['industries_created']}")
    print(f"  Industries skipped:    {result['industries_existing']}")
    print(f"  Survey types created:  {result['survey_types_created']}")
    print(f"  Survey types skipped:  {result['survey_types_existing']}")
    print("")

    for row in result.get("industry_details") or []:
        created = row.get("services_created") or []
        skipped = row.get("services_skipped") or []
        print(f"  {row.get('name')} ({row.get('slug')})")
        if created:
            print(f"    + created ({len(created)}): {', '.join(created[:5])}{'…' if len(created) > 5 else ''}")
        if skipped:
            print(f"    · skipped ({len(skipped)}): {', '.join(skipped[:5])}{'…' if len(skipped) > 5 else ''}")
        if not created and not skipped:
            print("    (no services defined)")
        print("")

    print("Done — re-run anytime; existing rows are never overwritten.")


if __name__ == "__main__":
    main()
