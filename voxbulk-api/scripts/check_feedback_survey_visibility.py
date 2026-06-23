#!/usr/bin/env python3
"""Compare admin survey types vs customer catalog (run on VPS after deploy).

Usage:
  cd voxbulk-api
  python scripts/check_feedback_survey_visibility.py
  python scripts/check_feedback_survey_visibility.py --name "Would recommend"
  python scripts/check_feedback_survey_visibility.py --industry-slug restaurants
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType
from app.services.customer_feedback.catalog_service import FeedbackCatalogService


def main() -> int:
    parser = argparse.ArgumentParser(description="Check customer feedback survey type visibility")
    parser.add_argument("--name", help="Filter survey type name (substring, case-insensitive)")
    parser.add_argument("--industry-slug", help="Filter by industry slug")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        industries = list(db.execute(select(FeedbackIndustry)).scalars().all())
        if args.industry_slug:
            industries = [i for i in industries if i.slug == args.industry_slug]
        if not industries:
            print("No industries matched.", file=sys.stderr)
            return 1

        any_issue = False
        for industry in industries:
            admin_rows = list(
                db.execute(
                    select(FeedbackSurveyType)
                    .where(FeedbackSurveyType.industry_id == industry.id)
                    .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
                ).scalars().all()
            )
            if args.name:
                needle = args.name.strip().lower()
                admin_rows = [r for r in admin_rows if needle in (r.name or "").lower()]

            catalog = FeedbackCatalogService.list_customer_catalog_survey_types(
                db, industry_id=industry.id
            )
            catalog_ids = {item["id"] for item in catalog}

            print(f"\n=== {industry.name} ({industry.slug}) ===")
            print(f"Admin rows: {len(admin_rows)} | Customer catalog: {len(catalog)}")

            for row in admin_rows:
                in_catalog = row.id in catalog_ids
                hidden = bool(getattr(row, "customer_hidden", False))
                status = "VISIBLE" if in_catalog else "hidden"
                if (not row.is_active or hidden) and in_catalog:
                    status = "BUG — disabled but in catalog"
                    any_issue = True
                elif row.is_active and not hidden and not in_catalog and not row.archived_at:
                    status = "not selectable (no sendable template?)"
                print(
                    f"  [{status}] {row.name!r} id={row.id[:8]}… "
                    f"is_active={row.is_active} customer_hidden={hidden} archived={bool(row.archived_at)}"
                )

        if any_issue:
            print("\nFound disabled types still in customer catalog — run ./deploy-vps.sh and restart API.", file=sys.stderr)
            return 2
        print("\nOK — no disabled types leaked into customer catalog.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
