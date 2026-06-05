#!/usr/bin/env python3
"""Seed WA Survey industries, service tags, and hidden system templates.

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
    print("OK — WA Survey industry catalog ready")
    print(f"  Industries created: {result['industries_created']} (existing: {result['industries_existing']})")
    print(f"  Service types created: {result['survey_types_created']} (existing: {result['survey_types_existing']})")
    for row in result.get("industries") or []:
        print(f"  - {row['name']} ({row['slug']}): {row['service_count']} services")


if __name__ == "__main__":
    main()
