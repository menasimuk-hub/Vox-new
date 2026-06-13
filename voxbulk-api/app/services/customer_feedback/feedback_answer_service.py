"""Normalize visitor answers for branching logic (Arabic → English)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES, resolve_template_language
from app.services.survey_wa_translation_service import SurveyWaTranslationService

POOR_ANSWERS = frozenset(
    {
        "poor",
        "unfriendly",
        "overpriced",
        "needs work",
        "too long",
        "slow",
        "unclear",
        "not for me",
        "unlikely",
        "no",
        "not worth it",
        "too crowded",
        "difficult",
        "needs improvement",
    }
)
OPT_IN_YES = frozenset({"yes", "yes please", "yes, please", "yes definitely", "yes, definitely"})
OPT_IN_NO = frozenset({"no", "no thanks", "no thank you", "no, thanks"})


def parse_template_buttons(tpl: FeedbackWaTemplate | None) -> list[str]:
    if tpl is None or not tpl.buttons_json:
        return []
    try:
        parsed = json.loads(tpl.buttons_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _english_template_for(db: Session, tpl: FeedbackWaTemplate | None) -> FeedbackWaTemplate | None:
    if tpl is None:
        return None
    if str(tpl.language or "").strip() in ENGLISH_TEMPLATE_LANGUAGES:
        return tpl
    if tpl.survey_type_id:
        return db.execute(
            select(FeedbackWaTemplate)
            .where(
                FeedbackWaTemplate.survey_type_id == tpl.survey_type_id,
                FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES),
                FeedbackWaTemplate.is_active.is_(True),
            )
            .order_by(FeedbackWaTemplate.step_order)
            .limit(1)
        ).scalar_one_or_none()
    return db.execute(
        select(FeedbackWaTemplate)
        .where(
            FeedbackWaTemplate.template_key == tpl.template_key,
            FeedbackWaTemplate.industry_id.is_(None),
            FeedbackWaTemplate.survey_type_id.is_(None),
            FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES),
            FeedbackWaTemplate.is_active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()


def map_answer_to_english_label(
    db: Session,
    *,
    answer: str,
    tpl: FeedbackWaTemplate | None,
    detected_language: str | None,
) -> str:
    """Map a reply (e.g. Arabic button label) to English for stored results and branching."""
    raw = str(answer or "").strip()
    if not raw:
        return ""
    lang = resolve_template_language(detected_language)
    if lang == "en_GB":
        return raw.lower()

    local_buttons = parse_template_buttons(tpl)
    en_tpl = _english_template_for(db, tpl)
    en_buttons = parse_template_buttons(en_tpl)
    if local_buttons and en_buttons:
        lowered = raw.lower()
        for idx, label in enumerate(local_buttons):
            if lowered == label.lower() and idx < len(en_buttons):
                return en_buttons[idx].lower()

    translated = SurveyWaTranslationService.translate_to_english(
        db,
        raw,
        detected_language=detected_language or "ar",
    )
    return str(translated.get("translated_text") or raw).strip().lower()


def is_negative_topic_answer(
    db: Session,
    *,
    answer: str,
    tpl: FeedbackWaTemplate | None,
    detected_language: str | None,
) -> bool:
    normalized = map_answer_to_english_label(
        db,
        answer=answer,
        tpl=tpl,
        detected_language=detected_language,
    )
    return normalized in POOR_ANSWERS


def is_opt_in_yes(
    db: Session,
    *,
    answer: str,
    tpl: FeedbackWaTemplate | None,
    detected_language: str | None,
) -> bool:
    normalized = map_answer_to_english_label(
        db,
        answer=answer,
        tpl=tpl,
        detected_language=detected_language,
    )
    return normalized in OPT_IN_YES


def is_opt_in_no(
    db: Session,
    *,
    answer: str,
    tpl: FeedbackWaTemplate | None,
    detected_language: str | None,
) -> bool:
    normalized = map_answer_to_english_label(
        db,
        answer=answer,
        tpl=tpl,
        detected_language=detected_language,
    )
    return normalized in OPT_IN_NO


def translate_answer_to_english(
    db: Session,
    *,
    answer: str,
    detected_language: str | None,
    tpl: FeedbackWaTemplate | None = None,
) -> dict[str, Any]:
    """Store English in results; keep original Arabic/other text."""
    original = str(answer or "").strip()
    if not original:
        return {"original_text": "", "answer_text_en": "", "translation_status": "skipped"}

    lang = resolve_template_language(detected_language)
    if lang == "en_GB":
        return {
            "original_text": original,
            "answer_text_en": original,
            "translation_status": "not_needed",
        }

    mapped = map_answer_to_english_label(
        db,
        answer=original,
        tpl=tpl,
        detected_language=detected_language,
    )
    if mapped and mapped != original.lower():
        return {
            "original_text": original,
            "answer_text_en": mapped,
            "translation_status": "button_mapped",
        }

    translated = SurveyWaTranslationService.translate_to_english(
        db,
        original,
        detected_language=detected_language or lang,
    )
    answer_en = str(translated.get("translated_text") or original).strip()
    return {
        "original_text": original,
        "answer_text_en": answer_en,
        "translation_status": translated.get("translation_status") or "completed",
    }
