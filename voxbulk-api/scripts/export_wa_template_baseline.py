#!/usr/bin/env python3
"""Export baseline WA template inventory (survey + feedback) for migration diff."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.wa_utility_migration import EXPECTED_WABA_ID, META_BUSINESS_PORTFOLIO_ID
from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template


def _survey_rows(db) -> list[dict]:
    rows = db.execute(
        select(TelnyxWhatsappTemplate, SurveyType.slug)
        .outerjoin(SurveyType, TelnyxWhatsappTemplate.survey_type_id == SurveyType.id)
        .where(TelnyxWhatsappTemplate.step_role == "abc_choice")
        .order_by(TelnyxWhatsappTemplate.name)
    ).all()
    out: list[dict] = []
    for tpl, survey_slug in rows:
        out.append(
            {
                "product": "survey",
                "name": tpl.name,
                "language": tpl.language or "en_GB",
                "industry_slug": survey_slug or "",
                "meta_category": tpl.category or "",
                "status": tpl.status or "",
                "telnyx_sync_status": tpl.local_sync_status or "",
                "telnyx_record_id": tpl.telnyx_record_id or "",
            }
        )
    return out


def _feedback_rows(db) -> list[dict]:
    rows = db.execute(
        select(FeedbackWaTemplate, FeedbackIndustry.slug)
        .outerjoin(FeedbackIndustry, FeedbackWaTemplate.industry_id == FeedbackIndustry.id)
        .order_by(FeedbackWaTemplate.template_key, FeedbackWaTemplate.language)
    ).all()
    out: list[dict] = []
    for tpl, industry_slug in rows:
        if is_marketing_wa_template(tpl):
            continue
        out.append(
            {
                "product": "feedback",
                "name": tpl.template_key or tpl.id,
                "template_key": tpl.template_key or "",
                "language": tpl.language or "en_GB",
                "industry_slug": industry_slug or "",
                "meta_category": tpl.meta_category or "",
                "status": tpl.telnyx_sync_status or "",
                "telnyx_sync_status": tpl.telnyx_sync_status or "",
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Export WA template baseline inventory")
    parser.add_argument(
        "--output",
        default=str(ROOT / "seed-data" / "wa-survey" / "migration-reports" / "baseline-inventory.json"),
        help="JSON output path",
    )
    parser.add_argument("--csv", help="Optional CSV output path")
    args = parser.parse_args()

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_sessionmaker()() as db:
        survey = _survey_rows(db)
        feedback = _feedback_rows(db)

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "waba_id": EXPECTED_WABA_ID,
        "meta_business_portfolio_id": META_BUSINESS_PORTFOLIO_ID,
        "counts": {
            "survey": len(survey),
            "feedback": len(feedback),
            "feedback_en": sum(1 for r in feedback if str(r["language"]).startswith("en")),
            "feedback_ar": sum(1 for r in feedback if str(r["language"]).startswith("ar")),
        },
        "rows": survey + feedback,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Survey: {len(survey)}  Feedback: {len(feedback)}")

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_absolute():
            csv_path = ROOT / csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(payload["rows"][0].keys()) if payload["rows"] else ["product", "name"]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(payload["rows"])
        print(f"Wrote {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
