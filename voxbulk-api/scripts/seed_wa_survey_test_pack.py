#!/usr/bin/env python3
"""Seed Services / General WA Survey test pack (local APPROVED templates, no OpenAI).

Usage:
  cd voxbulk-api
  python scripts/seed_wa_survey_test_pack.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService


def main() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        result = SurveyWaTestPackSeedService.ensure_test_pack(db)
    print("OK — WA Survey test pack ready")
    print(f"  Industry: {result['industry']['name']} ({result['industry']['slug']})")
    print(f"  Survey type: {result['survey_type']['name']} ({result['survey_type']['slug']})")
    print(f"  Templates: {result['template_count']} (created={result['created']}, updated={result['updated']})")


if __name__ == "__main__":
    main()
