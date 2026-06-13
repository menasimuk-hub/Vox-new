"""Build survey step sequences and resolve templates for Customer Feedback."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackSurveyType, FeedbackWaTemplate


SYSTEM_TEMPLATE_KEYS = frozenset({"open_question", "marketing_opt_in", "thank_you", "tell_us_more"})
ENGLISH_TEMPLATE_LANGUAGES = frozenset({"en_GB", "en", "en_US", "en_AU"})


def resolve_template_language(raw: str | None) -> str:
    lang = str(raw or "en_GB").strip().lower().replace("-", "_")
    if lang in {"ar", "arabic"}:
        return "ar"
    return "en_GB"


def get_system_template(db: Session, template_key: str, *, language: str | None = None) -> FeedbackWaTemplate | None:
    lang = resolve_template_language(language)
    base_q = (
        select(FeedbackWaTemplate)
        .where(
            FeedbackWaTemplate.is_active.is_(True),
            FeedbackWaTemplate.template_key == template_key,
            FeedbackWaTemplate.industry_id.is_(None),
            FeedbackWaTemplate.survey_type_id.is_(None),
        )
        .limit(1)
    )
    row = db.execute(base_q.where(FeedbackWaTemplate.language == lang)).scalar_one_or_none()
    if row is None and lang != "en_GB":
        row = db.execute(base_q.where(FeedbackWaTemplate.language == "en_GB")).scalar_one_or_none()
    return row


def parse_selected_type_ids(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("selected_survey_type_ids")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    single = str(payload.get("survey_type_id") or "").strip()
    return [single] if single else []


def build_survey_config(
    db: Session,
    *,
    industry_id: str,
    selected_type_ids: list[str],
    open_question_enabled: bool,
    marketing_opt_in_enabled: bool,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for type_id in selected_type_ids[:6]:
        row = db.get(FeedbackSurveyType, type_id)
        if row is None or row.industry_id != industry_id:
            continue
        steps.append({"kind": "topic", "survey_type_id": row.id, "template_key": row.slug})
    if open_question_enabled:
        steps.append({"kind": "open_question", "template_key": "open_question"})
    if marketing_opt_in_enabled:
        steps.append({"kind": "marketing_opt_in", "template_key": "marketing_opt_in"})
    steps.append({"kind": "thank_you", "template_key": "thank_you"})
    return {"steps": steps}


def load_survey_config(location: FeedbackLocation) -> dict[str, Any]:
    raw = getattr(location, "survey_config_json", None)
    if not raw:
        return {"steps": [{"kind": "topic", "survey_type_id": location.survey_type_id, "template_key": "overall-experience"}]}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"steps": []}


def template_for_step(
    db: Session,
    location: FeedbackLocation,
    step: dict[str, Any],
    *,
    language: str | None = None,
) -> FeedbackWaTemplate | None:
    lang = resolve_template_language(language)
    kind = str(step.get("kind") or "topic")
    if kind == "topic":
        survey_type_id = str(step.get("survey_type_id") or "").strip()
        if not survey_type_id:
            return None
        base_q = (
            select(FeedbackWaTemplate)
            .where(
                FeedbackWaTemplate.is_active.is_(True),
                FeedbackWaTemplate.survey_type_id == survey_type_id,
            )
            .order_by(FeedbackWaTemplate.step_order)
            .limit(1)
        )
        row = db.execute(base_q.where(FeedbackWaTemplate.language == lang)).scalar_one_or_none()
        if row is None and lang != "en_GB":
            row = db.execute(base_q.where(FeedbackWaTemplate.language == "en_GB")).scalar_one_or_none()
        return row
    template_key = str(step.get("template_key") or kind)
    return get_system_template(db, template_key, language=lang)


def format_template_message(tpl: FeedbackWaTemplate) -> str:
    body = str(tpl.body_text or "").strip()
    buttons: list[str] = []
    if tpl.buttons_json:
        try:
            parsed = json.loads(tpl.buttons_json)
            if isinstance(parsed, list):
                buttons = [str(b).strip() for b in parsed if str(b).strip()]
        except json.JSONDecodeError:
            buttons = []
    if not buttons:
        return body
    opts = " | ".join(buttons)
    prompt = "اختر:" if resolve_template_language(tpl.language) == "ar" else "Reply with:"
    return f"{body}\n\n{prompt} {opts}"
