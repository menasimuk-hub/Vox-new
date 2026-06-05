"""System survey templates — welcome, thank-you, tell-us-more under hidden industry."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import SYSTEM_SURVEY_INDUSTRY_SLUG, IndustryService
from app.services.survey_type_service import survey_type_to_dict
from app.services.survey_whatsapp_template_service import survey_template_to_dict

SYSTEM_TEMPLATE_KINDS = ("welcome", "thank_you", "tell_us_more")

SYSTEM_SURVEY_TYPES: list[dict[str, Any]] = [
    {
        "slug": "welcome_templates",
        "name": "Welcome templates",
        "system_template_kind": "welcome",
        "description": "Survey opening templates — customer picks one when creating a survey.",
        "sort_order": 10,
    },
    {
        "slug": "thank_you_template",
        "name": "Thank you templates",
        "system_template_kind": "thank_you",
        "description": "Survey closing templates — customer picks one when creating a survey.",
        "sort_order": 20,
    },
    {
        "slug": "tell_us_more",
        "name": "Tell us more",
        "system_template_kind": "tell_us_more",
        "description": "Low-rating follow-up prompt — applied automatically when score is low.",
        "sort_order": 30,
    },
]


class SurveySystemTemplateService:
    @staticmethod
    def ensure_system_industry(db: Session) -> Industry:
        IndustryService.ensure_defaults(db)
        row = db.execute(
            select(Industry).where(Industry.slug == SYSTEM_SURVEY_INDUSTRY_SLUG)
        ).scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = Industry(
                id=str(uuid.uuid4()),
                slug=SYSTEM_SURVEY_INDUSTRY_SLUG,
                name="System survey templates",
                description="Hidden industry for welcome, thank-you, and low-rating templates.",
                is_active=True,
                is_hidden=True,
                sort_order=9999,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:
                db.rollback()
                row = db.execute(
                    select(Industry).where(Industry.slug == SYSTEM_SURVEY_INDUSTRY_SLUG)
                ).scalar_one_or_none()
                if row is None:
                    raise
        elif not bool(getattr(row, "is_hidden", False)):
            row.is_hidden = True
            row.updated_at = now
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def ensure_system_survey_types(db: Session) -> list[SurveyType]:
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        now = datetime.utcnow()
        created: list[SurveyType] = []
        for item in SYSTEM_SURVEY_TYPES:
            existing = db.execute(
                select(SurveyType).where(
                    SurveyType.industry_id == industry.id,
                    SurveyType.slug == item["slug"],
                )
            ).scalar_one_or_none()
            if existing is not None:
                if not existing.system_template_kind:
                    existing.system_template_kind = item["system_template_kind"]
                    existing.updated_at = now
                    db.add(existing)
                created.append(existing)
                continue
            row = SurveyType(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                slug=item["slug"],
                name=item["name"],
                description=item.get("description"),
                is_active=True,
                default_length="standard",
                min_length=4,
                max_length=6,
                supports_anonymous=True,
                system_template_kind=item["system_template_kind"],
                sort_order=int(item.get("sort_order") or 100),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created.append(row)
        db.commit()
        return created

    @staticmethod
    def list_templates_for_builder(db: Session) -> dict[str, Any]:
        """Templates grouped by kind for dashboard survey builder."""
        SurveySystemTemplateService.ensure_system_survey_types(db)
        grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in SYSTEM_TEMPLATE_KINDS}
        types = list(
            db.execute(
                select(SurveyType).where(SurveyType.system_template_kind.in_(SYSTEM_TEMPLATE_KINDS))
            ).scalars()
        )
        for st in types:
            kind = str(st.system_template_kind or "").strip()
            if kind not in grouped:
                continue
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st.id)
                ).scalars()
            )
            for mapping in mappings:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None or not tpl.active_for_survey:
                    continue
                status = str(tpl.status or "").upper()
                grouped[kind].append(
                    {
                        **survey_template_to_dict(tpl),
                        "survey_type_id": st.id,
                        "survey_type_name": st.name,
                        "survey_type_slug": st.slug,
                        "is_approved": status == "APPROVED",
                    }
                )
        return {"ok": True, "templates": grouped}

    @staticmethod
    def resolve_tell_us_more_template_id(db: Session) -> int | None:
        SurveySystemTemplateService.ensure_system_survey_types(db)
        st = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == "tell_us_more").limit(1)
        ).scalar_one_or_none()
        if st is None:
            return None
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
            .where(
                SurveyTypeTemplate.survey_type_id == st.id,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        return int(row.id) if row is not None else None

    @staticmethod
    def list_admin(db: Session) -> dict[str, Any]:
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        types = SurveySystemTemplateService.ensure_system_survey_types(db)
        return {
            "ok": True,
            "industry": IndustryService.get_industry(db, industry.id),
            "survey_types": [survey_type_to_dict(t) for t in types],
        }
