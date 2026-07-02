"""Audit and deduplicate WA templates during UTILITY migration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.customer_feedback.feedback_template_translation_service import find_translated_template


def audit_all_wa_templates(db: Session) -> dict[str, Any]:
    survey_rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.survey_type_id.isnot(None))
        ).scalars()
    )
    interview_rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.sales_template_key.isnot(None))
        ).scalars()
    )
    feedback_rows = list(db.execute(select(FeedbackWaTemplate)).scalars())

    active_survey_type_ids = {
        str(row.id)
        for row in db.execute(select(SurveyType.id).where(SurveyType.is_active.is_(True))).scalars()
    }
    active_feedback_survey_ids = {
        str(row.id)
        for row in db.execute(select(FeedbackSurveyType.id).where(FeedbackSurveyType.is_active.is_(True))).scalars()
    }

    survey_abc = [r for r in survey_rows if str(r.step_role or "") == "abc_choice"]
    survey_orphans = [r for r in survey_abc if str(r.survey_type_id or "") not in active_survey_type_ids]
    survey_dup_groups = _survey_duplicate_groups(survey_abc)

    feedback_en = [r for r in feedback_rows if not is_marketing_wa_template(r) and str(r.language or "") in ENGLISH_TEMPLATE_LANGUAGES]
    feedback_missing_ar: list[dict[str, str]] = []
    for en in feedback_en:
        ar = find_translated_template(db, en, language="ar")
        if ar is None:
            feedback_missing_ar.append({"template_key": en.template_key, "id": en.id})

    feedback_orphans = [
        r for r in feedback_rows if r.survey_type_id and str(r.survey_type_id) not in active_feedback_survey_ids
    ]
    feedback_dup_groups = _feedback_duplicate_groups(feedback_rows)

    return {
        "survey": {
            "abc_choice_total": len(survey_abc),
            "orphan_count": len(survey_orphans),
            "duplicate_group_count": len(survey_dup_groups),
            "duplicate_rows": sum(len(g) - 1 for g in survey_dup_groups.values()),
            "orphans": [{"id": r.id, "name": r.name} for r in survey_orphans[:50]],
            "duplicate_groups": {
                key: [{"id": r.id, "name": r.name, "category": r.category} for r in rows]
                for key, rows in list(survey_dup_groups.items())[:30]
            },
        },
        "feedback": {
            "total": len(feedback_rows),
            "english_utility": len(feedback_en),
            "missing_ar_pair": len(feedback_missing_ar),
            "orphan_count": len(feedback_orphans),
            "duplicate_group_count": len(feedback_dup_groups),
            "missing_ar": feedback_missing_ar[:50],
        },
        "interview": {"total": len(interview_rows)},
    }


def _survey_duplicate_groups(rows: list[TelnyxWhatsappTemplate]) -> dict[str, list[TelnyxWhatsappTemplate]]:
    groups: dict[str, list[TelnyxWhatsappTemplate]] = defaultdict(list)
    for row in rows:
        if str(row.step_role or "") != "abc_choice":
            continue
        key = str(row.survey_type_id or "")
        if key:
            groups[key].append(row)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _feedback_duplicate_groups(rows: list[FeedbackWaTemplate]) -> dict[str, list[FeedbackWaTemplate]]:
    groups: dict[str, list[FeedbackWaTemplate]] = defaultdict(list)
    for row in rows:
        if is_marketing_wa_template(row):
            continue
        key = f"{row.survey_type_id or row.template_key}:{row.language}"
        groups[key].append(row)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _pick_canonical_survey_row(rows: list[TelnyxWhatsappTemplate]) -> TelnyxWhatsappTemplate:
    def score(row: TelnyxWhatsappTemplate) -> tuple[int, float]:
        cat = str(row.category or "").upper()
        utility_bonus = 0 if cat == "UTILITY" else 1
        ts = row.updated_at.timestamp() if row.updated_at else 0.0
        return (utility_bonus, -ts)

    return sorted(rows, key=score)[0]


def _pick_canonical_feedback_row(rows: list[FeedbackWaTemplate]) -> FeedbackWaTemplate:
    def score(row: FeedbackWaTemplate) -> tuple[int, float]:
        cat = str(row.meta_category or "").lower()
        utility_bonus = 0 if cat == "utility" else 1
        ts = row.updated_at.timestamp() if row.updated_at else 0.0
        return (utility_bonus, -ts)

    return sorted(rows, key=score)[0]


def deactivate_duplicate_and_orphan_templates(
    db: Session,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Deactivate duplicate abc_choice survey rows and orphan templates (keep one canonical each)."""
    now = datetime.utcnow()
    deactivated_survey: list[dict[str, Any]] = []
    deactivated_feedback: list[dict[str, Any]] = []

    survey_abc = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.survey_type_id.isnot(None),
                TelnyxWhatsappTemplate.step_role == "abc_choice",
            )
        ).scalars()
    )
    active_survey_type_ids = {
        str(row.id)
        for row in db.execute(select(SurveyType.id).where(SurveyType.is_active.is_(True))).scalars()
    }

    for row in survey_abc:
        if str(row.survey_type_id or "") not in active_survey_type_ids and row.active_for_survey:
            if not dry_run:
                row.active_for_survey = False
                row.updated_at = now
                db.add(row)
            deactivated_survey.append({"id": row.id, "name": row.name, "reason": "orphan_survey_type"})

    for _key, group in _survey_duplicate_groups(survey_abc).items():
        canonical = _pick_canonical_survey_row(group)
        for row in group:
            if row.id == canonical.id:
                continue
            if row.active_for_survey:
                if not dry_run:
                    row.active_for_survey = False
                    row.updated_at = now
                    db.add(row)
                deactivated_survey.append({"id": row.id, "name": row.name, "reason": "duplicate", "kept_id": canonical.id})

    feedback_rows = list(db.execute(select(FeedbackWaTemplate)).scalars())
    active_feedback_survey_ids = {
        str(row.id)
        for row in db.execute(select(FeedbackSurveyType.id).where(FeedbackSurveyType.is_active.is_(True))).scalars()
    }

    for row in feedback_rows:
        if is_marketing_wa_template(row):
            continue
        if row.survey_type_id and str(row.survey_type_id) not in active_feedback_survey_ids and row.is_active:
            if not dry_run:
                row.is_active = False
                row.updated_at = now
                db.add(row)
            deactivated_feedback.append({"id": row.id, "template_key": row.template_key, "reason": "orphan_survey_type"})

    for _key, group in _feedback_duplicate_groups(feedback_rows).items():
        canonical = _pick_canonical_feedback_row(group)
        for row in group:
            if row.id == canonical.id:
                continue
            if row.is_active:
                if not dry_run:
                    row.is_active = False
                    row.updated_at = now
                    db.add(row)
                deactivated_feedback.append(
                    {"id": row.id, "template_key": row.template_key, "reason": "duplicate", "kept_id": canonical.id}
                )

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "deactivated_survey": len(deactivated_survey),
        "deactivated_feedback": len(deactivated_feedback),
        "survey": deactivated_survey,
        "feedback": deactivated_feedback,
    }
