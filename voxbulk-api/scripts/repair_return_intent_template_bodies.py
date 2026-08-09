"""Align Return intent CF template bodies with the topic title (Meta Utility-safe).

Updates feedback_wa_templates where template_key = return-intent (en_GB + ar).
Does not push to Meta/Telnyx — re-sync templates after running if WA HSM must match.

  cd voxbulk-api && python scripts/repair_return_intent_template_bodies.py
  python scripts/repair_return_intent_template_bodies.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.services.wa_template_utility_content import (
    return_intent_utility_body,
    return_intent_utility_body_ar,
)


def _buttons_json(language: str) -> str:
    if str(language or "").lower().startswith("ar"):
        return json.dumps(["نعم", "لا"], ensure_ascii=False)
    return json.dumps(["Yes", "No"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_sessionmaker()()
    updated = 0
    try:
        rows = list(
            db.execute(
                select(FeedbackWaTemplate, FeedbackSurveyType, FeedbackIndustry)
                .join(FeedbackSurveyType, FeedbackSurveyType.id == FeedbackWaTemplate.survey_type_id)
                .outerjoin(FeedbackIndustry, FeedbackIndustry.id == FeedbackSurveyType.industry_id)
                .where(FeedbackWaTemplate.template_key == "return-intent")
            ).all()
        )
        for tpl, st, industry in rows:
            lang = str(tpl.language or "en_GB")
            if lang.startswith("ar"):
                new_body = return_intent_utility_body_ar()
            elif lang in {"en_GB", "en", "en_US", "en_AU"} or lang.startswith("en"):
                new_body = return_intent_utility_body(
                    industry_slug=getattr(industry, "slug", None),
                    industry_name=getattr(industry, "name", None),
                )
            else:
                # Keep other locales until translated; still fix EN/AR now.
                continue
            old = str(tpl.body_text or "").strip()
            if old == new_body and str(tpl.buttons_json or "") == _buttons_json(lang):
                continue
            print(
                f"{'DRY ' if args.dry_run else ''}"
                f"{getattr(industry, 'slug', '?')} {st.slug} {lang}:\n"
                f"  OLD: {old[:120]}\n"
                f"  NEW: {new_body}"
            )
            if not args.dry_run:
                tpl.body_text = new_body
                tpl.buttons_json = _buttons_json(lang)
                tpl.step_role = "yes_no"
                tpl.updated_at = datetime.utcnow()
                db.add(tpl)
                updated += 1
        if not args.dry_run:
            db.commit()
        print(f"updated={updated} scanned={len(rows)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
