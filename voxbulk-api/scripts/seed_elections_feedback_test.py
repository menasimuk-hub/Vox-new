#!/usr/bin/env python3
"""Seed or purge the throwaway elections Customer Feedback demo.

Restricted to jomlauk@gmail.com. Not listed in the dashboard wizard.
Does not push templates to Meta — WhatsApp is numbered session text.

Usage (from voxbulk-api, project venv):
  python scripts/seed_elections_feedback_test.py
  python scripts/seed_elections_feedback_test.py --purge
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import (
    FeedbackAiFollowUpJob,
    FeedbackConsentEvent,
    FeedbackIndustry,
    FeedbackIndustryOrganisation,
    FeedbackLocation,
    FeedbackMarketingSubscriber,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
    FeedbackVoiceNoteJob,
    FeedbackWaTemplate,
)
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.customer_feedback.elections_demo import (
    ELECTIONS_INDUSTRY_SLUG,
    ELECTIONS_LOCATION_NAME,
    ELECTIONS_OWNER_EMAIL,
    ELECTIONS_QUESTIONS,
    ELECTIONS_THANK_YOU,
    SESSION_MENU_ROLE,
)
from app.services.customer_feedback.location_service import (
    build_location_qr_token,
    location_to_dict,
)
from app.services.customer_feedback.survey_config_service import build_survey_config


def _owner_org_id(db) -> tuple[str, str]:
    email = ELECTIONS_OWNER_EMAIL.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"User {ELECTIONS_OWNER_EMAIL} not found.")
    preferred = str(getattr(user, "preferred_org_id", None) or "").strip()
    if preferred:
        org = db.get(Organisation, preferred)
        if org is not None:
            return user.id, org.id
    membership = db.execute(
        select(OrganisationMembership)
        .where(OrganisationMembership.user_id == user.id)
        .order_by(OrganisationMembership.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if membership is None:
        raise SystemExit(f"User {ELECTIONS_OWNER_EMAIL} has no organisation membership.")
    return user.id, membership.org_id


def _industry(db) -> FeedbackIndustry | None:
    return db.execute(
        select(FeedbackIndustry).where(FeedbackIndustry.slug == ELECTIONS_INDUSTRY_SLUG).limit(1)
    ).scalar_one_or_none()


def purge(db) -> None:
    industry = _industry(db)
    if industry is None:
        print("No elections industry found — nothing to purge.")
        return
    type_ids = list(
        db.execute(select(FeedbackSurveyType.id).where(FeedbackSurveyType.industry_id == industry.id)).scalars().all()
    )
    loc_ids = list(
        db.execute(select(FeedbackLocation.id).where(FeedbackLocation.industry_id == industry.id)).scalars().all()
    )
    sess_ids = []
    if loc_ids:
        sess_ids = list(
            db.execute(select(FeedbackSession.id).where(FeedbackSession.location_id.in_(loc_ids))).scalars().all()
        )
    resp_ids = []
    if sess_ids:
        resp_ids = list(
            db.execute(select(FeedbackResponse.id).where(FeedbackResponse.session_id.in_(sess_ids))).scalars().all()
        )
    if resp_ids:
        db.execute(delete(FeedbackVoiceNoteJob).where(FeedbackVoiceNoteJob.response_id.in_(resp_ids)))
    if sess_ids:
        db.execute(delete(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.session_id.in_(sess_ids)))
        db.execute(delete(FeedbackConsentEvent).where(FeedbackConsentEvent.session_id.in_(sess_ids)))
        db.execute(delete(FeedbackMarketingSubscriber).where(FeedbackMarketingSubscriber.session_id.in_(sess_ids)))
        db.execute(delete(FeedbackResponse).where(FeedbackResponse.session_id.in_(sess_ids)))
        db.execute(delete(FeedbackSession).where(FeedbackSession.id.in_(sess_ids)))
    if loc_ids:
        db.execute(delete(FeedbackConsentEvent).where(FeedbackConsentEvent.location_id.in_(loc_ids)))
        db.execute(delete(FeedbackMarketingSubscriber).where(FeedbackMarketingSubscriber.location_id.in_(loc_ids)))
        db.execute(delete(FeedbackLocation).where(FeedbackLocation.id.in_(loc_ids)))
    if type_ids:
        db.execute(delete(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id.in_(type_ids)))
        db.execute(delete(FeedbackSurveyType).where(FeedbackSurveyType.id.in_(type_ids)))
    db.execute(delete(FeedbackWaTemplate).where(FeedbackWaTemplate.industry_id == industry.id))
    db.execute(delete(FeedbackIndustryOrganisation).where(FeedbackIndustryOrganisation.industry_id == industry.id))
    db.delete(industry)
    db.commit()
    print("Purged elections demo industry, templates, location, and sessions.")


def seed(db) -> None:
    user_id, org_id = _owner_org_id(db)
    org = db.get(Organisation, org_id)
    now = datetime.utcnow()
    industry = _industry(db)
    if industry is None:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=ELECTIONS_INDUSTRY_SLUG,
            name=ELECTIONS_LOCATION_NAME,
            description="Throwaway elections demo — not in wizard.",
            is_active=True,
            visibility_mode="restricted",
            sort_order=9000,
            created_at=now,
            updated_at=now,
        )
        db.add(industry)
        db.flush()
    else:
        industry.name = ELECTIONS_LOCATION_NAME
        industry.visibility_mode = "restricted"
        industry.is_active = True
        industry.updated_at = now

    link = db.execute(
        select(FeedbackIndustryOrganisation).where(
            FeedbackIndustryOrganisation.industry_id == industry.id,
            FeedbackIndustryOrganisation.org_id == org_id,
        )
    ).scalar_one_or_none()
    if link is None:
        db.add(
            FeedbackIndustryOrganisation(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                org_id=org_id,
                created_at=now,
            )
        )

    type_ids: list[str] = []
    for index, item in enumerate(ELECTIONS_QUESTIONS):
        row = db.execute(
            select(FeedbackSurveyType).where(
                FeedbackSurveyType.industry_id == industry.id,
                FeedbackSurveyType.slug == item["slug"],
            )
        ).scalar_one_or_none()
        if row is None:
            row = FeedbackSurveyType(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                slug=item["slug"],
                name=item["name"],
                description=item["intro"],
                is_active=True,
                sort_order=(index + 1) * 10,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
        else:
            row.name = item["name"]
            row.description = item["intro"]
            row.is_active = True
            row.sort_order = (index + 1) * 10
            row.updated_at = now
        type_ids.append(row.id)

        tpl = db.execute(
            select(FeedbackWaTemplate).where(
                FeedbackWaTemplate.survey_type_id == row.id,
                FeedbackWaTemplate.language == "ar",
            )
        ).scalar_one_or_none()
        body = str(item["intro"])
        buttons = json.dumps(list(item["options"]), ensure_ascii=False)
        if tpl is None:
            tpl = FeedbackWaTemplate(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                survey_type_id=row.id,
                step_order=index + 1,
                template_key=item["slug"],
                body_text=body,
                step_role=SESSION_MENU_ROLE,
                language="ar",
                buttons_json=buttons,
                meta_category="utility",
                telnyx_sync_status="draft",
                sync_from_meta=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(tpl)
        else:
            tpl.body_text = body
            tpl.buttons_json = buttons
            tpl.step_role = SESSION_MENU_ROLE
            tpl.language = "ar"
            tpl.telnyx_sync_status = "draft"
            tpl.sync_from_meta = False
            tpl.is_active = True
            tpl.updated_at = now

    survey_config = build_survey_config(
        db,
        industry_id=industry.id,
        selected_type_ids=type_ids,
        open_question_enabled=False,
        marketing_opt_in_enabled=False,
    )
    survey_config["web_theme"] = {"base_template_id": "elections"}
    survey_config["force_language"] = "ar"
    survey_config["thank_you_text"] = ELECTIONS_THANK_YOU

    location = db.execute(
        select(FeedbackLocation).where(
            FeedbackLocation.org_id == org_id,
            FeedbackLocation.industry_id == industry.id,
        )
    ).scalar_one_or_none()
    company = org.name if org else "Your business"
    if location is None:
        qr_token = build_location_qr_token(company=company, branch=ELECTIONS_LOCATION_NAME)
        location = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=type_ids[0],
            name=ELECTIONS_LOCATION_NAME,
            qr_token=qr_token,
            wa_sender_country="ps",
            status="preview",
            selected_survey_type_ids_json=json.dumps(type_ids),
            open_question_enabled=False,
            marketing_opt_in_enabled=False,
            survey_config_json=json.dumps(survey_config, ensure_ascii=False),
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(location)
    else:
        location.name = ELECTIONS_LOCATION_NAME
        location.survey_type_id = type_ids[0]
        location.selected_survey_type_ids_json = json.dumps(type_ids)
        location.open_question_enabled = False
        location.marketing_opt_in_enabled = False
        location.survey_config_json = json.dumps(survey_config, ensure_ascii=False)
        location.wa_sender_country = "ps"
        location.updated_at = now
    db.commit()
    db.refresh(location)
    payload = location_to_dict(db, location)
    print("Elections demo ready (hidden from wizard).")
    print(f"  org_id:          {org_id}")
    print(f"  location_id:     {location.id}")
    print(f"  web:             {payload.get('web_survey_url')}")
    print(f"  whatsapp:        {payload.get('wa_url')}")
    print(f"  qr_image:        {payload.get('qr_image_url')}")
    print(f"  qr_token:        {location.qr_token}")
    print("  Results: Jomla dashboard → Customer Feedback → Results")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or purge the elections CF demo.")
    parser.add_argument("--purge", action="store_true", help="Delete the demo industry, QR, templates, and sessions.")
    args = parser.parse_args()
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        if args.purge:
            purge(db)
        else:
            seed(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
