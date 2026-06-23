#!/usr/bin/env python3
"""Compare admin vs customer catalog for WA Survey and Customer Feedback.

Usage:
  cd voxbulk-api
  python scripts/check_feedback_survey_visibility.py
  python scripts/check_feedback_survey_visibility.py --name "Team collaboration"
  python scripts/check_feedback_survey_visibility.py --product wa-survey
  python scripts/check_feedback_survey_visibility.py --product customer-feedback
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
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.wa_survey_visibility_service import list_wa_survey_customer_catalog_types


def _print_wa_survey(db, *, name: str | None, industry_slug: str | None) -> bool:
    any_issue = False
    industries = list(db.execute(select(Industry)).scalars().all())
    if industry_slug:
        industries = [i for i in industries if i.slug == industry_slug]
    print("\n=== WA Survey (main Surveys wizard) ===")
    if not industries:
        print("No industries matched.")
        return False
    for industry in industries:
        admin_rows = list(
            db.execute(
                select(SurveyType)
                .where(SurveyType.industry_id == industry.id, SurveyType.system_template_kind.is_(None))
                .order_by(SurveyType.sort_order, SurveyType.name)
            ).scalars().all()
        )
        if name:
            needle = name.strip().lower()
            admin_rows = [r for r in admin_rows if needle in (r.name or "").lower() or needle in (r.slug or "").lower()]
        catalog = list_wa_survey_customer_catalog_types(db, industry_id=industry.id)
        catalog_ids = {item["id"] for item in catalog}
        print(f"\n--- {industry.name} ({industry.slug}) ---")
        print(f"Admin rows: {len(admin_rows)} | Customer catalog: {len(catalog)}")
        for row in admin_rows:
            in_catalog = row.id in catalog_ids
            hidden = bool(getattr(row, "customer_hidden", False))
            disabled = not row.is_active or hidden
            status = "VISIBLE" if in_catalog else "hidden"
            if disabled and in_catalog:
                status = "BUG — disabled but in catalog"
                any_issue = True
            elif row.is_active and not hidden and not in_catalog:
                status = "not selectable (no sendable template?)"
            print(
                f"  [{status}] {row.name!r} slug={row.slug} "
                f"is_active={row.is_active} customer_hidden={hidden}"
            )
    return any_issue


def _print_customer_feedback(db, *, name: str | None, industry_slug: str | None) -> bool:
    any_issue = False
    industries = list(db.execute(select(FeedbackIndustry)).scalars().all())
    if industry_slug:
        industries = [i for i in industries if i.slug == industry_slug]
    print("\n=== Customer Feedback (QR feedback wizard) ===")
    if not industries:
        print("No industries matched.")
        return False
    for industry in industries:
        admin_rows = list(
            db.execute(
                select(FeedbackSurveyType)
                .where(FeedbackSurveyType.industry_id == industry.id)
                .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
            ).scalars().all()
        )
        if name:
            needle = name.strip().lower()
            admin_rows = [
                r for r in admin_rows if needle in (r.name or "").lower() or needle in (r.slug or "").lower()
            ]
        catalog = FeedbackCatalogService.list_customer_catalog_survey_types(db, industry_id=industry.id)
        catalog_ids = {item["id"] for item in catalog}
        print(f"\n--- {industry.name} ({industry.slug}) ---")
        print(f"Admin rows: {len(admin_rows)} | Customer catalog: {len(catalog)}")
        for row in admin_rows:
            in_catalog = row.id in catalog_ids
            hidden = bool(getattr(row, "customer_hidden", False))
            disabled = not row.is_active or hidden or bool(row.archived_at)
            status = "VISIBLE" if in_catalog else "hidden"
            if disabled and in_catalog:
                status = "BUG — disabled but in catalog"
                any_issue = True
            elif row.is_active and not hidden and not in_catalog and not row.archived_at:
                status = "not selectable (no sendable template?)"
            print(
                f"  [{status}] {row.name!r} slug={row.slug} "
                f"is_active={row.is_active} customer_hidden={hidden} archived={bool(row.archived_at)}"
            )
    return any_issue


def main() -> int:
    parser = argparse.ArgumentParser(description="Check survey type visibility for both products")
    parser.add_argument("--name", help="Filter by name or slug substring")
    parser.add_argument("--industry-slug", help="Filter by industry slug")
    parser.add_argument(
        "--product",
        choices=("all", "wa-survey", "customer-feedback"),
        default="all",
        help="Which product to check (default: both)",
    )
    args = parser.parse_args()

    any_issue = False
    with get_sessionmaker()() as db:
        if args.product in {"all", "wa-survey"}:
            any_issue = _print_wa_survey(db, name=args.name, industry_slug=args.industry_slug) or any_issue
        if args.product in {"all", "customer-feedback"}:
            any_issue = (
                _print_customer_feedback(db, name=args.name, industry_slug=args.industry_slug) or any_issue
            )

    if any_issue:
        print("\nFound disabled types still in a customer catalog.", file=sys.stderr)
        return 2
    print("\nOK — no disabled types leaked into customer catalogs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
