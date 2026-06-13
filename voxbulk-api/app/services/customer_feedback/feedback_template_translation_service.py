"""Translate Customer Feedback WhatsApp templates via DeepSeek."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackWaTemplate
from app.services.agents.base import AgentMessage
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    list_feedback_templates_for_industry,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

TARGET_LANGUAGE = "ar"
_TRANSLATE_SYSTEM = (
    "You translate WhatsApp customer-feedback survey templates into Modern Standard Arabic "
    "suitable for Gulf and Levant audiences. Preserve tone (polite, concise). "
    "Keep any leading emoji from the source. "
    "Return ONLY valid JSON: "
    '{"body":"Arabic body text","buttons":["btn1","btn2","btn3"]} '
    "Use the same number of buttons as the source (empty array if none). "
    "Each button must be at most 20 characters."
)


class FeedbackTemplateTranslationError(Exception):
    pass


def _parse_translation_json(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_buttons(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def translate_template_content(
    db: Session,
    *,
    body_text: str,
    buttons: list[str],
    template_key: str,
    use_deepseek: bool = True,
) -> dict[str, Any]:
    body = str(body_text or "").strip()
    if not body:
        raise FeedbackTemplateTranslationError("Empty body_text")
    if not use_deepseek:
        return {"body": body, "buttons": buttons[:3]}

    user_prompt = (
        f"Template key: {template_key}\n"
        f"Source BODY:\n{body}\n\n"
        f"Source buttons: {json.dumps(buttons, ensure_ascii=False)}"
    )
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=_TRANSLATE_SYSTEM,
            messages=[AgentMessage(role="user", content=user_prompt)],
            max_tokens=700,
            temperature=0.2,
            provider="deepseek",
        )
        parsed = _parse_translation_json(result.assistant_text)
        if not parsed:
            raise ValueError("model did not return JSON")
        translated_body = str(parsed.get("body") or "").strip()
        if not translated_body:
            raise ValueError("empty translated body")
        raw_buttons = parsed.get("buttons")
        translated_buttons: list[str] = []
        if isinstance(raw_buttons, list):
            translated_buttons = [str(item).strip()[:20] for item in raw_buttons if str(item).strip()]
        elif buttons:
            translated_buttons = buttons[:3]
        return {"body": translated_body, "buttons": translated_buttons[:3]}
    except Exception as exc:
        logger.warning("feedback_template_translate_failed key=%s err=%s", template_key, str(exc)[:200])
        raise FeedbackTemplateTranslationError(str(exc)) from exc


def find_translated_template(
    db: Session,
    source: FeedbackWaTemplate,
    *,
    language: str = TARGET_LANGUAGE,
) -> FeedbackWaTemplate | None:
    lang = str(language or TARGET_LANGUAGE).strip()
    if source.survey_type_id:
        return db.execute(
            select(FeedbackWaTemplate)
            .where(
                FeedbackWaTemplate.survey_type_id == source.survey_type_id,
                FeedbackWaTemplate.language == lang,
            )
            .limit(1)
        ).scalar_one_or_none()
    return db.execute(
        select(FeedbackWaTemplate)
        .where(
            FeedbackWaTemplate.template_key == source.template_key,
            FeedbackWaTemplate.industry_id.is_(None),
            FeedbackWaTemplate.survey_type_id.is_(None),
            FeedbackWaTemplate.language == lang,
        )
        .limit(1)
    ).scalar_one_or_none()


def upsert_arabic_template(
    db: Session,
    source: FeedbackWaTemplate,
    *,
    body_text: str,
    buttons: list[str],
) -> FeedbackWaTemplate:
    now = datetime.utcnow()
    existing = find_translated_template(db, source, language=TARGET_LANGUAGE)
    payload = {
        "body_text": body_text,
        "buttons_json": json.dumps(buttons, ensure_ascii=False),
        "step_role": source.step_role,
        "meta_category": source.meta_category,
        "step_order": source.step_order,
        "is_active": True,
        "telnyx_sync_status": "draft",
        "updated_at": now,
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    row = FeedbackWaTemplate(
        id=str(uuid.uuid4()),
        industry_id=source.industry_id,
        survey_type_id=source.survey_type_id,
        step_order=source.step_order,
        template_key=source.template_key,
        body_text=body_text,
        step_role=source.step_role,
        language=TARGET_LANGUAGE,
        buttons_json=json.dumps(buttons, ensure_ascii=False),
        meta_category=source.meta_category,
        telnyx_sync_status="draft",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_english_source_templates(
    db: Session,
    *,
    industry_slug: str | None = None,
) -> list[FeedbackWaTemplate]:
    q = select(FeedbackWaTemplate).where(FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES))
    if industry_slug:
        industry = db.execute(
            select(FeedbackIndustry).where(FeedbackIndustry.slug == str(industry_slug).strip().lower()).limit(1)
        ).scalar_one_or_none()
        if industry is None:
            raise FeedbackTemplateTranslationError(f"Industry not found: {industry_slug}")
        ids = {row.id for row in list_feedback_templates_for_industry(db, industry.id)}
        if not ids:
            return []
        q = q.where(FeedbackWaTemplate.id.in_(ids))
    return list(db.execute(q.order_by(FeedbackWaTemplate.template_key)).scalars().all())


def translate_templates_to_arabic(
    db: Session,
    *,
    industry_slug: str | None = None,
    force: bool = False,
    use_deepseek: bool = True,
    push_telnyx: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    sources = list_english_source_templates(db, industry_slug=industry_slug)
    if limit is not None and limit > 0:
        sources = sources[:limit]

    translated = 0
    skipped = 0
    pushed = 0
    push_failed = 0
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for source in sources:
        label = source.template_key
        if not force:
            existing = find_translated_template(db, source, language=TARGET_LANGUAGE)
            if existing and str(existing.body_text or "").strip():
                skipped += 1
                results.append({"template_key": label, "status": "skipped", "template_id": existing.id})
                if push_telnyx and not dry_run:
                    try:
                        push_feedback_template_to_telnyx(db, existing, dry_run=False)
                        pushed += 1
                    except FeedbackTelnyxPushError as exc:
                        push_failed += 1
                        errors.append({"template_key": label, "stage": "push", "error": str(exc)})
                continue

        buttons = _parse_buttons(source.buttons_json)
        try:
            content = translate_template_content(
                db,
                body_text=source.body_text,
                buttons=buttons,
                template_key=source.template_key,
                use_deepseek=use_deepseek,
            )
        except FeedbackTemplateTranslationError as exc:
            errors.append({"template_key": label, "stage": "translate", "error": str(exc)})
            continue

        if dry_run:
            translated += 1
            results.append(
                {
                    "template_key": label,
                    "status": "dry_run",
                    "body_preview": str(content.get("body") or "")[:120],
                    "buttons": content.get("buttons") or [],
                }
            )
            continue

        row = upsert_arabic_template(
            db,
            source,
            body_text=str(content.get("body") or ""),
            buttons=list(content.get("buttons") or []),
        )
        translated += 1
        results.append({"template_key": label, "status": "translated", "template_id": row.id})

        if push_telnyx:
            try:
                push_feedback_template_to_telnyx(db, row, dry_run=False)
                pushed += 1
            except FeedbackTelnyxPushError as exc:
                push_failed += 1
                errors.append({"template_key": label, "stage": "push", "error": str(exc)})

    return {
        "ok": not errors and push_failed == 0,
        "industry_slug": industry_slug,
        "source_count": len(sources),
        "translated": translated,
        "skipped": skipped,
        "pushed": pushed,
        "push_failed": push_failed,
        "dry_run": dry_run,
        "errors": errors,
        "results": results,
        "message": (
            f"{'Validated' if dry_run else 'Translated'} {translated}, skipped {skipped}"
            + (f", pushed {pushed}" if push_telnyx else "")
            + (f", {len(errors) + push_failed} failed" if errors or push_failed else "")
        ),
    }
