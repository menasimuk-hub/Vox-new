#!/usr/bin/env python3
"""Rebuild survey_config_json for Customer Feedback locations from flags + selected topics.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/backfill_feedback_survey_config.py --dry-run
  python scripts/backfill_feedback_survey_config.py
  python scripts/backfill_feedback_survey_config.py --org-id UUID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackLocation
from app.services.customer_feedback.survey_config_service import (
    repair_survey_config_if_needed,
    survey_config_needs_rebuild,
)
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Customer Feedback survey_config_json")
    parser.add_argument("--org-id", help="Limit to one organisation UUID")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        q = select(FeedbackLocation).order_by(FeedbackLocation.created_at.asc())
        if args.org_id:
            q = q.where(FeedbackLocation.org_id == str(args.org_id).strip())
        rows = list(db.execute(q).scalars().all())
        needs = 0
        repaired = 0
        for row in rows:
            steps = None
            raw = row.survey_config_json
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
                        steps = parsed["steps"]
                except json.JSONDecodeError:
                    pass
            if not survey_config_needs_rebuild(row, steps):
                continue
            needs += 1
            print(f"repair location={row.id} org={row.org_id} name={row.name!r}")
            if args.dry_run:
                continue
            if repair_survey_config_if_needed(db, row):
                repaired += 1

    print(f"\nChecked {len(rows)} location(s); {needs} need repair; {repaired} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
