"""Push Customer Feedback WhatsApp templates to Telnyx / Meta."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    normalize_wa_template_category,
    prepare_components_for_telnyx_push,
)
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_voice_service import _telnyx_config, _telnyx_headers, resolve_telnyx_whatsapp_waba_id
from app.services.telnyx_whatsapp_template_sync_service import TELNYX_WHATSAPP_TEMPLATES_URL

logger = logging.getLogger(__name__)

META_QUICK_REPLY_MAX = 3
META_BUTTON_MAX_LEN = 20


class FeedbackTelnyxPushError(Exception):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


def _slug_underscore(text: str, *, max_len: int = 32) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return (base or "item")[:max_len]


def parse_feedback_buttons(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("text") or "").strip()
        else:
            label = str(item or "").strip()
        if label:
            out.append(label[:META_BUTTON_MAX_LEN])
    return out[:META_QUICK_REPLY_MAX]


def build_feedback_components(tpl: FeedbackWaTemplate) -> list[dict[str, Any]]:
    body = str(tpl.body_text or "").strip()
    if not body:
        raise FeedbackTelnyxPushError("Template body_text is empty.")
    components: list[dict[str, Any]] = [{"type": "BODY", "text": body}]
    buttons = parse_feedback_buttons(tpl.buttons_json)
    if buttons:
        components.append(
            {
                "type": "BUTTONS",
                "buttons": [{"type": "QUICK_REPLY", "text": label} for label in buttons],
            }
        )
    return components


def feedback_meta_template_name(
    tpl: FeedbackWaTemplate,
    *,
    industry_slug: str | None = None,
    survey_type_slug: str | None = None,
) -> str:
    parts = ["voxbulk", "cf"]
    if industry_slug:
        parts.append(_slug_underscore(industry_slug))
    if survey_type_slug:
        parts.append(_slug_underscore(survey_type_slug))
    parts.append(_slug_underscore(tpl.template_key or "template"))
    parts.append(re.sub(r"[^a-z0-9]", "", str(tpl.id or "").lower())[:8])
    return "_".join(p for p in parts if p)[:512]


def normalize_feedback_language(raw: str | None) -> str:
    lang = str(raw or "en_GB").strip().replace("-", "_")
    if lang.lower() in {"en", "english"}:
        return "en_GB"
    return lang or "en_GB"


def push_feedback_template_to_telnyx(
    db: Session,
    tpl: FeedbackWaTemplate,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    industry_slug: str | None = None
    survey_slug: str | None = None
    if tpl.industry_id:
        ind = db.get(FeedbackIndustry, tpl.industry_id)
        industry_slug = ind.slug if ind else None
    if tpl.survey_type_id:
        st = db.get(FeedbackSurveyType, tpl.survey_type_id)
        survey_slug = st.slug if st else None

    raw_components = build_feedback_components(tpl)
    try:
        components = prepare_components_for_telnyx_push(raw_components, row=None)
    except SurveyWhatsappTemplateError as exc:
        raise FeedbackTelnyxPushError(str(exc)) from exc

    category = normalize_wa_template_category(tpl.meta_category or "utility", required=True)
    language = normalize_feedback_language(tpl.language)
    name = feedback_meta_template_name(tpl, industry_slug=industry_slug, survey_type_slug=survey_slug)

    if dry_run:
        payload = {
            "name": name,
            "category": category,
            "language": language,
            "waba_id": "(dry-run — not sent)",
            "components": components,
        }
        return {
            "ok": True,
            "dry_run": True,
            "template_id": tpl.id,
            "template_key": tpl.template_key,
            "meta_name": name,
            "category": category,
            "language": language,
            "payload": payload,
            "message": "Dry run — payload validated, not sent to Telnyx.",
        }

    config = _telnyx_config(db)
    api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
    if not api_key:
        api_key, _ = require_telnyx_api_key(db)
    waba_id = resolve_telnyx_whatsapp_waba_id(db, config)
    if not waba_id:
        raise FeedbackTelnyxPushError(
            "WhatsApp Business Account ID is not configured. "
            "Set it in Admin → Integrations → Telnyx → WhatsApp."
        )

    payload = {
        "name": name,
        "category": category,
        "language": language,
        "waba_id": waba_id,
        "components": components,
    }

    result: dict[str, Any] = {
        "ok": False,
        "dry_run": False,
        "template_id": tpl.id,
        "template_key": tpl.template_key,
        "meta_name": name,
        "category": category,
        "language": language,
        "waba_id": waba_id,
        "payload": payload,
    }

    try:
        with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
            response = client.post(
                TELNYX_WHATSAPP_TEMPLATES_URL,
                headers=_telnyx_headers(api_key),
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise FeedbackTelnyxPushError(f"HTTP error calling Telnyx: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:2000]}

    result["status_code"] = response.status_code
    result["telnyx_response"] = body

    if response.status_code >= 400:
        detail = body
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                detail = errors[0]
            elif body.get("detail"):
                detail = body.get("detail")
        raise FeedbackTelnyxPushError(
            f"Telnyx rejected template (HTTP {response.status_code}): {detail}",
            payload=result,
        )

    now = datetime.utcnow()
    tpl.telnyx_sync_status = "submitted"
    tpl.updated_at = now
    db.add(tpl)
    db.commit()
    db.refresh(tpl)

    record_id = None
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            record_id = data.get("id") or data.get("record_id")

    result["ok"] = True
    result["message"] = "Template submitted to Telnyx for Meta approval."
    result["telnyx_record_id"] = record_id
    result["telnyx_sync_status"] = tpl.telnyx_sync_status
    return result


def load_feedback_template(
    db: Session,
    *,
    template_id: str | None = None,
    template_key: str | None = None,
) -> FeedbackWaTemplate:
    if template_id:
        row = db.get(FeedbackWaTemplate, str(template_id).strip())
        if row is None:
            raise FeedbackTelnyxPushError(f"Template not found: {template_id}")
        return row
    key = str(template_key or "").strip()
    if not key:
        raise FeedbackTelnyxPushError("Provide template_id or template_key.")
    row = db.execute(
        select(FeedbackWaTemplate)
        .where(FeedbackWaTemplate.template_key == key)
        .order_by(FeedbackWaTemplate.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise FeedbackTelnyxPushError(f"No feedback template with key: {key}")
    return row


def resolve_feedback_industry(
    db: Session,
    *,
    industry_id: str | None = None,
    industry_slug: str | None = None,
) -> FeedbackIndustry:
    if industry_id:
        row = db.get(FeedbackIndustry, str(industry_id).strip())
        if row is None:
            raise FeedbackTelnyxPushError(f"Industry not found: {industry_id}")
        return row
    slug = str(industry_slug or "").strip().lower()
    if not slug:
        raise FeedbackTelnyxPushError("Provide industry_id or industry_slug.")
    row = db.execute(
        select(FeedbackIndustry).where(FeedbackIndustry.slug == slug).limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise FeedbackTelnyxPushError(f"No feedback industry with slug: {slug}")
    return row


def list_feedback_templates_for_industry(db: Session, industry_id: str) -> list[FeedbackWaTemplate]:
    return list(
        db.execute(
            select(FeedbackWaTemplate)
            .join(
                FeedbackSurveyType,
                FeedbackWaTemplate.survey_type_id == FeedbackSurveyType.id,
                isouter=True,
            )
            .where(FeedbackWaTemplate.industry_id == industry_id)
            .order_by(
                FeedbackSurveyType.sort_order.nulls_last(),
                FeedbackWaTemplate.step_order,
                FeedbackWaTemplate.template_key,
            )
        ).scalars().all()
    )


def push_all_feedback_templates_for_industry(
    db: Session,
    *,
    industry_id: str | None = None,
    industry_slug: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    industry = resolve_feedback_industry(db, industry_id=industry_id, industry_slug=industry_slug)
    templates = list_feedback_templates_for_industry(db, industry.id)
    if not templates:
        return {
            "ok": True,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "pushed": 0,
            "failed": 0,
            "dry_run": dry_run,
            "errors": [],
            "results": [],
            "message": f"No templates found for industry {industry.name!r}. Import english-templates.md first.",
        }

    pushed = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for tpl in templates:
        label = f"{tpl.template_key} ({tpl.id[:8]})"
        try:
            result = push_feedback_template_to_telnyx(db, tpl, dry_run=dry_run)
            pushed += 1
            results.append(
                {
                    "ok": True,
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "meta_name": result.get("meta_name"),
                    "message": result.get("message"),
                }
            )
        except FeedbackTelnyxPushError as exc:
            failed += 1
            err = {
                "template_id": tpl.id,
                "template_key": tpl.template_key,
                "error": str(exc),
                "payload": getattr(exc, "payload", None) or {},
            }
            errors.append(err)
            results.append({"ok": False, **err})

    return {
        "ok": failed == 0,
        "industry_id": industry.id,
        "industry_slug": industry.slug,
        "industry_name": industry.name,
        "template_count": len(templates),
        "pushed": pushed,
        "failed": failed,
        "dry_run": dry_run,
        "errors": errors,
        "results": results,
        "message": (
            f"{'Validated' if dry_run else 'Pushed'} {pushed}/{len(templates)} template(s) "
            f"for {industry.name}"
            + (f", {failed} failed" if failed else "")
        ),
    }
