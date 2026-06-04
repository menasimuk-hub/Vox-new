"""Seed a local APPROVED WA Survey test pack (Services / General / privacy off) — no OpenAI."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.survey_industry_scope import apply_industry_to_template
from app.services.survey_outcome_template_service import default_outcome_variables
from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import VARIANT_STANDARD
from app.services.wa_template_privacy import PRIVACY_MODE_OFF

TEST_INDUSTRY_SLUG = "services"
TEST_INDUSTRY_NAME = "Services"
TEST_SURVEY_TYPE_SLUG = "general"
TEST_SURVEY_TYPE_NAME = "General"

_LOCAL_PREFIX = "local_test_"

# Full 12-template pack: start + 8 middle + 3 completions (P3 outcome_key on completion rows).
TEST_PACK_SPECS: list[dict[str, Any]] = [
    {"step_role": "start", "title": "Test intro", "body": "Hi {{1}}, {{2}} would like your feedback. Ref {{3}}."},
    {"step_role": "rating", "title": "Rating", "body": "How would you rate your experience, {{1}}? (0–10)"},
    {"step_role": "yes_no", "title": "Yes / No", "body": "Would you recommend {{2}} to a friend, {{1}}?"},
    {"step_role": "helpfulness", "title": "Helpfulness", "body": "How helpful was our team today, {{1}}?"},
    {"step_role": "abc_choice", "title": "Choice", "body": "Which best describes your visit, {{1}}?"},
    {"step_role": "reason", "title": "Reason", "body": "What was the main reason for your score, {{1}}?"},
    {"step_role": "feeling_word", "title": "Feeling", "body": "Which word best describes how you feel, {{1}}?"},
    {"step_role": "follow_up", "title": "Follow-up", "body": "Anything else we should know, {{1}}?"},
    {"step_role": "improvement", "title": "Improvement", "body": "What could {{2}} improve, {{1}}?"},
    {"step_role": "completion", "outcome_key": "happy", "title": "Close — happy", "body": "Thanks {{1}} — we're glad {{2}} met your expectations."},
    {"step_role": "completion", "outcome_key": "neutral", "title": "Close — neutral", "body": "Thanks {{1}} — your feedback for {{2}} has been recorded."},
    {"step_role": "completion", "outcome_key": "unhappy", "title": "Close — unhappy", "body": "Sorry to hear that, {{1}}. {{2}} will review your feedback."},
]


def _components(body: str, *, with_start_button: bool = False) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [
        {"type": "BODY", "text": body, "example": {"body_text": [["Alex", "Acme Services", "REF-1"]]}},
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]
    if with_start_button:
        parts.append({"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}]})
    return parts


def _ensure_industry(db: Session) -> Industry:
    IndustryService.ensure_defaults(db)
    row = IndustryService.get_by_slug(db, TEST_INDUSTRY_SLUG)
    if row is not None:
        return row
    return IndustryService.create_industry(
        db,
        {
            "slug": TEST_INDUSTRY_SLUG,
            "name": TEST_INDUSTRY_NAME,
            "description": "Professional and consumer services feedback.",
            "sort_order": 35,
            "is_active": True,
        },
    )


def _get_survey_type(db: Session, *, industry_id: str) -> SurveyType | None:
    return (
        db.execute(
            select(SurveyType).where(
                SurveyType.slug == TEST_SURVEY_TYPE_SLUG,
                SurveyType.industry_id == industry_id,
            )
        )
        .scalars()
        .first()
    )


def _ensure_survey_type(db: Session, *, industry: Industry) -> SurveyType:
    row = _get_survey_type(db, industry_id=industry.id)
    if row is not None:
        return row
    now = datetime.utcnow()
    row = SurveyType(
        id=str(uuid.uuid4()),
        industry_id=industry.id,
        slug=TEST_SURVEY_TYPE_SLUG,
        name=TEST_SURVEY_TYPE_NAME,
        description="General-purpose feedback survey for internal testing.",
        is_active=True,
        default_length="standard",
        min_length=4,
        max_length=6,
        supports_anonymous=True,
        sort_order=5,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _template_name(survey_slug: str, spec: dict[str, Any]) -> str:
    role = str(spec["step_role"])
    ok = spec.get("outcome_key")
    if ok:
        return f"voxbulk_survey_{survey_slug}_{role}_{ok}"
    return f"voxbulk_survey_{survey_slug}_{role}"


def _find_existing(
    db: Session,
    *,
    survey_type_id: str,
    name: str,
) -> TelnyxWhatsappTemplate | None:
    return (
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.survey_type_id == survey_type_id,
                TelnyxWhatsappTemplate.name == name,
            )
        )
        .scalars()
        .first()
    )


def _upsert_template(
    db: Session,
    *,
    survey_type: SurveyType,
    spec: dict[str, Any],
) -> TelnyxWhatsappTemplate:
    role = normalize_step_role(str(spec["step_role"]))
    outcome_key = str(spec.get("outcome_key") or "").strip().lower() or None
    name = _template_name(survey_type.slug, spec)
    existing = _find_existing(db, survey_type_id=survey_type.id, name=name)
    body = str(spec.get("body") or "")
    components = _components(body, with_start_button=(role == "start"))
    now = datetime.utcnow()
    outcome_vars = default_outcome_variables(outcome_key) if outcome_key else None

    if existing is not None:
        existing.display_name = str(spec.get("title") or existing.display_name)[:128]
        existing.step_role = role
        existing.outcome_key = outcome_key
        existing.outcome_variables_json = json.dumps(outcome_vars) if outcome_vars else None
        existing.status = "APPROVED"
        existing.variant_type = VARIANT_STANDARD
        existing.privacy_mode = PRIVACY_MODE_OFF
        existing.body_preview = body[:500]
        existing.components_json = json.dumps(components)
        existing.draft_components_json = json.dumps(components)
        existing.example_values_json = json.dumps(["Alex", "Acme Services", "REF-1"])
        existing.active_for_survey = True
        existing.local_sync_status = "in_sync"
        existing.updated_at = now
        row = existing
    else:
        local_id = f"{_LOCAL_PREFIX}{uuid.uuid4().hex}"
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=name,
            display_name=str(spec.get("title") or role)[:128],
            language="en_US",
            category="UTILITY",
            status="APPROVED",
            variant_type=VARIANT_STANDARD,
            privacy_mode=PRIVACY_MODE_OFF,
            step_role=role,
            outcome_key=outcome_key,
            outcome_variables_json=json.dumps(outcome_vars) if outcome_vars else None,
            survey_type_id=survey_type.id,
            industry_id=survey_type.industry_id,
            body_preview=body[:500],
            components_json=json.dumps(components),
            draft_components_json=json.dumps(components),
            example_values_json=json.dumps(["Alex", "Acme Services", "REF-1"]),
            local_sync_status="in_sync",
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        apply_industry_to_template(row, survey_type)

    is_default = role == "start" or (role == "completion" and outcome_key == "neutral")
    SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=row.id,
        usable_as_standard=True,
        is_default_standard=is_default,
    )
    db.commit()
    db.refresh(row)
    return row


class SurveyWaTestPackSeedService:
    @staticmethod
    def ensure_test_pack(db: Session) -> dict[str, Any]:
        """Create or refresh Services / General / off test pack (12 templates)."""
        industry = _ensure_industry(db)
        survey_type = _ensure_survey_type(db, industry=industry)
        created = 0
        updated = 0
        templates: list[dict[str, Any]] = []

        for spec in TEST_PACK_SPECS:
            name = _template_name(survey_type.slug, spec)
            existed = _find_existing(db, survey_type_id=survey_type.id, name=name) is not None
            row = _upsert_template(db, survey_type=survey_type, spec=spec)
            if existed:
                updated += 1
            else:
                created += 1
            templates.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "step_role": row.step_role,
                    "outcome_key": row.outcome_key,
                    "status": row.status,
                }
            )

        bank_roles = {normalize_step_role(r) for r in MIDDLE_STEP_ROLES}
        bank_roles.update({"start", "completion"})

        return {
            "ok": True,
            "industry": {"id": industry.id, "slug": industry.slug, "name": industry.name},
            "survey_type": {"id": survey_type.id, "slug": survey_type.slug, "name": survey_type.name},
            "privacy_mode": PRIVACY_MODE_OFF,
            "template_count": len(templates),
            "created": created,
            "updated": updated,
            "templates": templates,
            "middle_roles": list(MIDDLE_STEP_ROLES),
        }

    @staticmethod
    def resolve_test_survey_type(db: Session) -> SurveyType | None:
        industry = IndustryService.get_by_slug(db, TEST_INDUSTRY_SLUG)
        if industry is None:
            return None
        return _get_survey_type(db, industry_id=industry.id)
