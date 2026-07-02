#!/usr/bin/env python3
"""Import utility-safe seed MD into DB before UTILITY migration phases."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.customer_feedback.template_import_service import FeedbackTemplateImportService
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_wa_md_seed_service import SurveyWaMdSeedService


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed survey + feedback utility templates into DB")
    parser.add_argument("--survey", action="store_true", help="Seed WA Survey from all-industries MD")
    parser.add_argument("--feedback", action="store_true", help="Import Customer Feedback english-templates.md")
    parser.add_argument("--replace-feedback", action="store_true", help="Replace existing feedback template bodies")
    parser.add_argument("--all", action="store_true", help="Run both survey and feedback seed")
    args = parser.parse_args()

    run_survey = args.survey or args.all
    run_feedback = args.feedback or args.all
    if not run_survey and not run_feedback:
        parser.error("Specify --survey, --feedback, or --all")

    md_survey = ROOT / "seed-data" / "wa-survey" / "all-industries-abc-templates.md"
    md_feedback = ROOT / "seed-data" / "customer-feedback" / "english-templates.md"

    with get_sessionmaker()() as db:
        if run_survey:
            SurveyIndustrySeedService.ensure_catalog(db)
            summary = SurveyWaMdSeedService.seed_all_industries_from_markdown_file(db, md_path=md_survey)
            print(f"Survey seed: {summary}")
        if run_feedback:
            summary = FeedbackTemplateImportService.import_from_md(
                db,
                md_path=md_feedback,
                replace_existing=bool(args.replace_feedback),
            )
            print(f"Feedback import: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
