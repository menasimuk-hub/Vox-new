"""Translate Customer Feedback WhatsApp templates via OpenAI structured JSON."""

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
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    list_feedback_templates_for_industry,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_utility_rewrite_service import _extract_leading_emoji, _prepend_leading_emoji
from app.services.wa_template_utility_lint import lint_utility_template

logger = logging.getLogger(__name__)

TARGET_LANGUAGE = "ar"
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)

_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "body": {
            "type": "string",
            "description": "Arabic template body without any emoji",
        },
        "buttons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Arabic quick-reply labels without emoji, max 20 chars each",
        },
    },
    "required": ["body", "buttons"],
    "additionalProperties": False,
}

_TRANSLATE_SYSTEM = (
    "You translate WhatsApp customer-feedback survey templates into Modern Standard Arabic "
    "for Gulf and Levant audiences. Tone: polite, concise, natural. "
    "Meta UTILITY rules: tie to a specific recent visit/order/appointment; "
    "no promotional language (no offers, discounts, loyalty, refer-a-friend, upsell). "
    "Do NOT include any emoji in body or buttons — emoji is added separately by the system. "
    "Translate only the text; preserve meaning and button count/order."
)


class FeedbackTemplateTranslationError(Exception):
    pass


def _strip_all_emoji(text: str) -> str:
    cleaned = _EMOJI_RE.sub("", str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def finalize_translated_body(*, source_body: str, translated_body: str) -> str:
    """Keep the source leading emoji at the start; never leave emoji mid/end of Arabic text."""
    leading_emoji, _ = _extract_leading_emoji(source_body)
    plain = _strip_all_emoji(translated_body)
    if not plain:
        raise FeedbackTemplateTranslationError("Translated body is empty after emoji cleanup")
    return _prepend_leading_emoji(leading_emoji, plain)


def finalize_translated_buttons(buttons: list[str]) -> list[str]:
    out: list[str] = []
    for label in buttons:
        clean = _strip_all_emoji(str(label or ""))
        if clean:
            out.append(clean[:20])
    return out[:3]


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
    use_llm: bool = True,
    provider: str = "openai",
) -> dict[str, Any]:
    body = str(body_text or "").strip()
    if not body:
        raise FeedbackTemplateTranslationError("Empty body_text")
    if not use_llm:
        return {
            "body": finalize_translated_body(source_body=body, translated_body=body),
            "buttons": finalize_translated_buttons(buttons),
        }

    leading_emoji, body_without_emoji = _extract_leading_emoji(body)
    source_buttons = [_strip_all_emoji(label) for label in buttons if _strip_all_emoji(label)]

    user_prompt = (
        f"Template key: {template_key}\n"
        f"Source BODY (no emoji):\n{body_without_emoji or body}\n\n"
        f"Source buttons (no emoji): {json.dumps(source_buttons, ensure_ascii=False)}\n\n"
        + (f"Note: source had leading emoji {leading_emoji!r} — do not include it in body.\n" if leading_emoji else "")
        + f"Return exactly {len(source_buttons)} button label(s)."
    )

    try:
        if provider == "openai":
            parsed, _meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=_TRANSLATE_SYSTEM,
                user_prompt=user_prompt,
                json_schema=_TRANSLATION_SCHEMA,
                schema_name="feedback_template_ar",
                max_output_tokens=900,
                temperature=0.2,
            )
        else:
            from app.services.agents.base import AgentMessage

            result = OpenAIProviderService.complete(
                db,
                system_prompt=_TRANSLATE_SYSTEM + ' Return JSON: {"body":"...","buttons":["..."]}',
                messages=[AgentMessage(role="user", content=user_prompt)],
                max_tokens=700,
                temperature=0.2,
                provider=provider,
            )
            raw = str(result.assistant_text or "").strip()
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise ValueError("model did not return JSON")
            parsed = json.loads(match.group(0))

        translated_body = finalize_translated_body(
            source_body=body,
            translated_body=str(parsed.get("body") or ""),
        )
        raw_buttons = parsed.get("buttons")
        translated_buttons: list[str] = []
        if isinstance(raw_buttons, list):
            translated_buttons = finalize_translated_buttons(
                [str(item).strip() for item in raw_buttons if str(item).strip()]
            )
        if not translated_buttons and source_buttons:
            translated_buttons = finalize_translated_buttons(source_buttons)
        return {"body": translated_body, "buttons": translated_buttons[:3]}
    except Exception as exc:
        logger.warning(
            "feedback_template_translate_failed key=%s provider=%s err=%s",
            template_key,
            provider,
            str(exc)[:200],
        )
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
    body_text = finalize_translated_body(source_body=source.body_text, translated_body=body_text)
    buttons = finalize_translated_buttons(buttons)
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
    use_llm: bool = True,
    provider: str = "openai",
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
                use_llm=use_llm,
                provider=provider,
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
        ar_buttons = list(content.get("buttons") or [])
        ar_lint = lint_utility_template(
            body=row.body_text,
            buttons=ar_buttons,
            language=TARGET_LANGUAGE,
            meta_category="utility",
            template_key=source.template_key,
            require_transaction_anchor=False,
        )
        if not ar_lint.ok:
            msgs = "; ".join(i.message for i in ar_lint.issues)
            errors.append({"template_key": label, "stage": "lint_ar", "error": msgs})
            continue
        translated += 1
        results.append({"template_key": label, "status": "translated", "template_id": row.id})

        if push_telnyx:
            try:
                result = push_feedback_template_to_telnyx(db, row, dry_run=False)
                if result.get("skipped_push") or result.get("linked"):
                    pushed += 1
                else:
                    pushed += 1
            except FeedbackTelnyxPushError as exc:
                push_failed += 1
                errors.append({"template_key": label, "stage": "push", "error": str(exc)})

    return {
        "ok": not errors and push_failed == 0,
        "industry_slug": industry_slug,
        "provider": provider,
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
