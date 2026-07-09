"""Push Customer Feedback WhatsApp templates to Telnyx / Meta."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    normalize_wa_template_category,
    prepare_components_for_telnyx_push,
)
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_voice_service import _telnyx_config, _telnyx_headers, resolve_telnyx_whatsapp_waba_id
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService, TELNYX_WHATSAPP_TEMPLATES_URL
from app.services.wa_template_meta_sync import META_SUBCODE_CONTENT_ALREADY_EXISTS, parse_meta_error_from_provider_detail
from app.services.wa_template_utility_lint import assert_utility_template

logger = logging.getLogger(__name__)

META_QUICK_REPLY_MAX = 3
META_BUTTON_MAX_LEN = 20
META_SUBCODE_CATEGORY_MISMATCH = 2388026
CF_META_NAME_VERSION = "v1"


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
    components: list[dict[str, Any]] = [
        {"type": "BODY", "text": body},
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]
    buttons = parse_feedback_buttons(tpl.buttons_json)
    if buttons:
        components.append(
            {
                "type": "BUTTONS",
                "buttons": [{"type": "QUICK_REPLY", "text": label} for label in buttons],
            }
        )
    return components


def _cfs_lang_slug(raw: str | None) -> str:
    """Short lang token for cfs_* Meta names (matches db-rebuild: en, zh, ar, …)."""
    lang = str(raw or "en_GB").strip().replace("-", "_")
    lowered = lang.lower()
    if lowered.startswith("en"):
        return "en"
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("pt"):
        return "pt"
    if lowered in {"nb", "no"}:
        return "no"
    head = lowered.split("_", 1)[0]
    return head or "en"


def feedback_meta_template_name(
    tpl: FeedbackWaTemplate,
    *,
    industry_slug: str | None = None,
    survey_type_slug: str | None = None,
    name_anchor_id: str | None = None,
) -> str:
    """Canonical Meta name: cfs_{industry}_{topic}_{lang}_v1 (one name per language row)."""
    del name_anchor_id  # legacy param — cfs names include language, no shared anchor
    stored = str(getattr(tpl, "meta_template_name", "") or "").strip()
    if stored:
        return stored[:512]
    ind = _slug_underscore(industry_slug) if str(industry_slug or "").strip() else ""
    key = _slug_underscore(tpl.template_key or survey_type_slug or "template")
    lang = _cfs_lang_slug(tpl.language)
    parts = ["cfs"]
    if ind:
        parts.append(ind)
    parts.extend([key, lang, CF_META_NAME_VERSION])
    return "_".join(p for p in parts if p)[:512]


def preview_feedback_meta_template_name(
    *,
    industry_slug: str,
    survey_type_slug: str,
) -> str:
    """Human-readable Meta name before DB rows exist."""
    key = _slug_underscore(survey_type_slug)
    ind = _slug_underscore(industry_slug)
    return f"cfs_{ind}_{key}_en_{CF_META_NAME_VERSION}"[:512]


def english_anchor_template(db: Session, tpl: FeedbackWaTemplate) -> FeedbackWaTemplate:
    """Meta template name is shared across languages — anchor on the English row."""
    if str(tpl.language or "").strip() in ENGLISH_TEMPLATE_LANGUAGES:
        return tpl
    if tpl.survey_type_id:
        row = db.execute(
            select(FeedbackWaTemplate)
            .where(
                FeedbackWaTemplate.survey_type_id == tpl.survey_type_id,
                FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES),
            )
            .order_by(FeedbackWaTemplate.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row
    if tpl.template_key and tpl.industry_id is None and tpl.survey_type_id is None:
        row = db.execute(
            select(FeedbackWaTemplate)
            .where(
                FeedbackWaTemplate.template_key == tpl.template_key,
                FeedbackWaTemplate.industry_id.is_(None),
                FeedbackWaTemplate.survey_type_id.is_(None),
                FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES),
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row
    return tpl


def _remote_language_matches(item: dict[str, Any], language: str) -> bool:
    item_lang = str(item.get("language") or "").replace("-", "_").lower()
    target = normalize_feedback_language(language).lower()
    if item_lang == target:
        return True
    if target == "ar" and item_lang.startswith("ar"):
        return True
    if target.startswith("en") and item_lang.startswith("en"):
        return True
    return False


def _remote_templates_for_name(remote_items: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    target = str(name or "").strip().lower()
    return [
        item
        for item in remote_items
        if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == target
    ]


def find_remote_feedback_template(
    remote_items: list[dict[str, Any]],
    *,
    name: str,
    language: str | None = None,
) -> dict[str, Any] | None:
    matches = _remote_templates_for_name(remote_items, name)
    if language:
        for item in matches:
            if _remote_language_matches(item, language):
                return item
        return None
    return matches[0] if matches else None


def resolve_feedback_push_category(
    tpl: FeedbackWaTemplate,
    remote_items: list[dict[str, Any]],
    *,
    meta_name: str,
) -> str:
    for item in _remote_templates_for_name(remote_items, meta_name):
        remote_category = normalize_wa_template_category(item.get("category"), required=False)
        if remote_category:
            return remote_category
    return normalize_wa_template_category(tpl.meta_category or "utility", required=True)


def _extract_telnyx_error_detail(body: Any) -> str:
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("detail") or first)
            return str(first)
        if body.get("detail"):
            return str(body.get("detail"))
    return str(body)


def _mark_template_submitted(db: Session, tpl: FeedbackWaTemplate) -> None:
    now = datetime.utcnow()
    tpl.telnyx_sync_status = "submitted"
    tpl.updated_at = now
    db.add(tpl)
    db.commit()
    db.refresh(tpl)


def map_remote_meta_status_to_local(remote_status: str | None) -> str:
    status = str(remote_status or "").strip().upper()
    if status == "APPROVED":
        return "approved"
    if status in {"PENDING", "IN_APPEAL"}:
        return "pending"
    if status == "REJECTED":
        return "rejected"
    if status == "PAUSED":
        return "paused"
    if status:
        return "submitted"
    return "draft"


def _apply_remote_status(db: Session, tpl: FeedbackWaTemplate, remote: dict[str, Any]) -> str:
    from app.services.wa_system_template_routing_service import WaSystemTemplateRoutingService

    WaSystemTemplateRoutingService.apply_feedback_remote_content_to_row(db, tpl, remote)
    local_status = map_remote_meta_status_to_local(remote.get("status"))
    now = datetime.utcnow()
    tpl.telnyx_sync_status = local_status
    tpl.updated_at = now
    db.add(tpl)
    return local_status


def normalize_feedback_language(raw: str | None) -> str:
    lang = str(raw or "en_GB").strip().replace("-", "_")
    lowered = lang.lower()
    if lowered in {"en", "english"}:
        return "en_GB"
    if lowered in {"ar", "arabic"}:
        return "ar"
    return lang or "en_GB"


def _feedback_meta_name_for_template(db: Session, tpl: FeedbackWaTemplate) -> str:
    industry_slug: str | None = None
    survey_slug: str | None = None
    if tpl.industry_id:
        ind = db.get(FeedbackIndustry, tpl.industry_id)
        industry_slug = ind.slug if ind else None
    if tpl.survey_type_id:
        st = db.get(FeedbackSurveyType, tpl.survey_type_id)
        survey_slug = st.slug if st else None
    return feedback_meta_template_name(
        tpl,
        industry_slug=industry_slug,
        survey_type_slug=survey_slug,
    )


def _feedback_template_needs_push(
    db: Session,
    tpl: FeedbackWaTemplate,
    remote_items: list[dict[str, Any]],
) -> bool:
    """Skip approved on Meta + unchanged local rows during industry batch sync."""
    if not str(tpl.body_text or "").strip():
        return False
    local_status = str(tpl.telnyx_sync_status or "draft").lower()
    if local_status in {"draft", "rejected", "needs_resubmit", "error", "local_changes"}:
        return True
    meta_name = _feedback_meta_name_for_template(db, tpl)
    language = normalize_feedback_language(tpl.language)
    existing = find_remote_feedback_template(remote_items, name=meta_name, language=language)
    if existing is None:
        return True
    remote_status = str(existing.get("status") or "").upper()
    if remote_status in {"REJECTED", "PAUSED"}:
        return True
    if remote_status == "APPROVED" and local_status in {"approved", "submitted", "synced", "in_sync", "pending"}:
        return False
    return True


def push_feedback_template_to_telnyx(
    db: Session,
    tpl: FeedbackWaTemplate,
    *,
    dry_run: bool = False,
    remote_items: list[dict[str, Any]] | None = None,
    connection_profile_id: str | None = None,
    service_code: str = "customer_feedback",
    force_push: bool = False,
) -> dict[str, Any]:
    industry_slug: str | None = None
    survey_slug: str | None = None
    if tpl.industry_id:
        ind = db.get(FeedbackIndustry, tpl.industry_id)
        industry_slug = ind.slug if ind else None
    if tpl.survey_type_id:
        st = db.get(FeedbackSurveyType, tpl.survey_type_id)
        survey_slug = st.slug if st else None

    name = feedback_meta_template_name(
        tpl,
        industry_slug=industry_slug,
        survey_type_slug=survey_slug,
    )

    if not is_marketing_wa_template(tpl):
        tpl.meta_category = "utility"
        db.add(tpl)
        db.flush()

    raw_components = build_feedback_components(tpl)
    if not is_marketing_wa_template(tpl):
        try:
            assert_utility_template(
                body=str(tpl.body_text or ""),
                buttons=parse_feedback_buttons(tpl.buttons_json),
                language=tpl.language,
                meta_category=tpl.meta_category or "utility",
                template_key=tpl.template_key,
                require_transaction_anchor=str(tpl.language or "").lower().startswith("en"),
            )
        except ValueError as exc:
            raise FeedbackTelnyxPushError(str(exc)) from exc
    try:
        components = prepare_components_for_telnyx_push(raw_components, row=None)
    except SurveyWhatsappTemplateError as exc:
        raise FeedbackTelnyxPushError(str(exc)) from exc

    language = normalize_feedback_language(tpl.language)

    prefetched = remote_items
    if prefetched is None and not dry_run:
        try:
            prefetched = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                allow_account_waba_fallback=not bool(connection_profile_id),
            )
        except Exception as exc:
            logger.warning("feedback_meta_prefetch_failed: %s", str(exc)[:200])
            prefetched = []

    category = resolve_feedback_push_category(tpl, prefetched or [], meta_name=name)

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
            "message": "Dry run — payload validated, not sent to Meta.",
        }

    existing_remote = find_remote_feedback_template(prefetched or [], name=name, language=language)
    if existing_remote and not force_push:
        _mark_template_submitted(db, tpl)
        return {
            "ok": True,
            "linked": True,
            "skipped_push": True,
            "template_id": tpl.id,
            "template_key": tpl.template_key,
            "meta_name": name,
            "category": category,
            "language": language,
            "telnyx_record_id": existing_remote.get("id"),
            "telnyx_sync_status": tpl.telnyx_sync_status,
            "message": "Already on Meta for this language — linked, not re-created.",
        }

    from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

    if is_meta_whatsapp_primary(
        db,
        service_code=service_code,
        connection_profile_id=connection_profile_id,
    ):
        from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService

        try:
            item = MetaWhatsappTemplateService.push_template_payload(
                db,
                name=name,
                language=language,
                category=category,
                components=components,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        except MetaWhatsappTemplateError as exc:
            raise FeedbackTelnyxPushError(str(exc), payload=getattr(exc, "payload", None)) from exc
        _mark_template_submitted(db, tpl)
        return {
            "ok": True,
            "dry_run": False,
            "template_id": tpl.id,
            "template_key": tpl.template_key,
            "meta_name": name,
            "category": category,
            "language": language,
            "telnyx_record_id": item.get("id"),
            "telnyx_sync_status": tpl.telnyx_sync_status,
            "message": "Template submitted to Meta for approval.",
        }

    if connection_profile_id:
        from app.services.connection.config_resolver import resolve_whatsapp_route_by_profile_id

        route = resolve_whatsapp_route_by_profile_id(
            db,
            connection_profile_id,
            service_code=service_code,
        )
        if route.is_meta:
            raise FeedbackTelnyxPushError("Connection profile uses Meta, not Telnyx.")
        config = route.config
    else:
        config = _telnyx_config(db)
    api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
    if not api_key:
        api_key, _ = require_telnyx_api_key(db)
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

    waba_hint = None
    if connection_profile_id and not WaTemplateProfilePushService.is_primary_profile(
        db,
        connection_profile_id,
        service_code=service_code,
    ):
        waba_hint = None
    waba_id = resolve_telnyx_whatsapp_waba_id(db, config, template_waba_id=waba_hint)
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

    response = _post_feedback_template_to_telnyx(api_key=api_key, payload=payload)
    status_code = int(response["status_code"])
    body = response["body"]
    result["status_code"] = status_code
    result["telnyx_response"] = body

    if status_code >= 400:
        detail_text = _extract_telnyx_error_detail(body)
        meta = parse_meta_error_from_provider_detail(detail_text)
        subcode = meta.get("subcode")

        if subcode == META_SUBCODE_CONTENT_ALREADY_EXISTS:
            _mark_template_submitted(db, tpl)
            result["ok"] = True
            result["linked"] = True
            result["skipped_push"] = True
            result["message"] = "Arabic content already exists on Meta for this template — treated as linked."
            result["telnyx_sync_status"] = tpl.telnyx_sync_status
            return result

        if subcode == META_SUBCODE_CATEGORY_MISMATCH:
            remote_category = resolve_feedback_push_category(tpl, prefetched or [], meta_name=name)
            local_category = normalize_wa_template_category(tpl.meta_category or "utility", required=True)
            if remote_category != local_category:
                payload["category"] = remote_category
                result["category"] = remote_category
                retry = _post_feedback_template_to_telnyx(api_key=api_key, payload=payload)
                status_code = int(retry["status_code"])
                body = retry["body"]
                result["status_code"] = status_code
                result["telnyx_response"] = body
                if status_code >= 400:
                    detail_text = _extract_telnyx_error_detail(body)
                    meta = parse_meta_error_from_provider_detail(detail_text)
                    if meta.get("subcode") == META_SUBCODE_CONTENT_ALREADY_EXISTS:
                        _mark_template_submitted(db, tpl)
                        result["ok"] = True
                        result["linked"] = True
                        result["skipped_push"] = True
                        result["message"] = (
                            "Category adjusted to match Meta; Arabic content already exists — linked."
                        )
                        result["telnyx_sync_status"] = tpl.telnyx_sync_status
                        return result

    if status_code >= 400:
        raise FeedbackTelnyxPushError(
            f"Telnyx rejected template (HTTP {status_code}): {_extract_telnyx_error_detail(body)}",
            payload=result,
        )

    _mark_template_submitted(db, tpl)

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


def _post_feedback_template_to_telnyx(*, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    transient_statuses = {429, 500, 502, 503, 504}
    last_exc: FeedbackTelnyxPushError | None = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
                response = client.post(
                    TELNYX_WHATSAPP_TEMPLATES_URL,
                    headers=_telnyx_headers(api_key),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            last_exc = FeedbackTelnyxPushError(f"HTTP error calling Telnyx: {exc}")
            if attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise last_exc from exc

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:2000]}
        if response.status_code not in transient_statuses or attempt >= 3:
            return {"status_code": response.status_code, "body": body}
        time.sleep(5 * attempt)
    if last_exc is not None:
        raise last_exc
    return {"status_code": 503, "body": {"errors": [{"detail": "Telnyx transient error retries exhausted"}]}}


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
    survey_type_ids = select(FeedbackSurveyType.id).where(FeedbackSurveyType.industry_id == industry_id)
    return list(
        db.execute(
            select(FeedbackWaTemplate)
            .join(
                FeedbackSurveyType,
                FeedbackWaTemplate.survey_type_id == FeedbackSurveyType.id,
                isouter=True,
            )
            .where(
                or_(
                    FeedbackWaTemplate.industry_id == industry_id,
                    FeedbackWaTemplate.survey_type_id.in_(survey_type_ids),
                )
            )
            .order_by(
                case((FeedbackSurveyType.sort_order.is_(None), 1), else_=0),
                FeedbackSurveyType.sort_order,
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
    linked = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    remote_items: list[dict[str, Any]] | None = None
    if not dry_run:
        try:
            remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:
            logger.warning("feedback_telnyx_bulk_prefetch_failed: %s", str(exc)[:200])
            remote_items = []

    for tpl in templates:
        try:
            result = push_feedback_template_to_telnyx(
                db,
                tpl,
                dry_run=dry_run,
                remote_items=remote_items,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                force_push=force_push,
            )
            pushed += 1
            if result.get("skipped_push") or result.get("linked"):
                linked += 1
            results.append(
                {
                    "ok": True,
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "meta_name": result.get("meta_name"),
                    "message": result.get("message"),
                    "linked": bool(result.get("linked")),
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
        "linked": linked,
        "failed": failed,
        "dry_run": dry_run,
        "errors": errors,
        "results": results,
        "message": (
            f"{'Validated' if dry_run else 'Pushed'} {pushed}/{len(templates)} template(s) "
            f"for {industry.name}"
            + (f" ({linked} already on Meta)" if linked else "")
            + (f", {failed} failed" if failed else "")
        ),
    }


def list_all_feedback_platform_templates(db: Session) -> list[FeedbackWaTemplate]:
    rows = list(
        db.execute(
            select(FeedbackWaTemplate)
            .where(FeedbackWaTemplate.is_active.is_(True))
            .order_by(
                FeedbackWaTemplate.industry_id,
                FeedbackWaTemplate.survey_type_id,
                FeedbackWaTemplate.step_order,
                FeedbackWaTemplate.template_key,
                FeedbackWaTemplate.language,
            )
        ).scalars().all()
    )
    return [
        tpl
        for tpl in rows
        if not is_marketing_wa_template(tpl) and str(tpl.body_text or "").strip()
    ]


def push_feedback_platform_batch(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 10,
    force_push: bool = False,
    connection_profile_id: str | None = None,
    industry_id: str | None = None,
    service_code: str = "customer_feedback",
) -> dict[str, Any]:
    """Hub or industry batch — push changed (default) or mirror-all (force_push) for Customer Feedback."""
    if industry_id:
        industry = resolve_feedback_industry(db, industry_id=industry_id)
        work = list_feedback_templates_for_industry(db, industry.id)
        scope_label = industry.name
    else:
        industry = None
        work = list_all_feedback_platform_templates(db)
        scope_label = "all customer feedback templates"

    work = [tpl for tpl in work if not is_marketing_wa_template(tpl) and str(tpl.body_text or "").strip()]
    total = len(work)
    if total == 0:
        return {
            "ok": True,
            "total": 0,
            "processed": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
            "next_offset": 0,
            "pushed": 0,
            "linked": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "results": [],
            "content_updated": 0,
            "error_count": 0,
            "message": f"No customer feedback templates to sync ({scope_label}).",
        }

    start = max(0, int(offset or 0))
    batch_limit = max(1, min(int(limit or 10), 50))
    slice_rows = work[start : start + batch_limit]

    remote_items: list[dict[str, Any]] | None = None
    try:
        remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
            allow_account_waba_fallback=not bool(connection_profile_id),
        )
    except Exception as exc:
        logger.warning("feedback_platform_prefetch_failed: %s", str(exc)[:200])
        remote_items = []

    pushed = 0
    linked = 0
    skipped = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for tpl in slice_rows:
        if not force_push and not _feedback_template_needs_push(db, tpl, remote_items or []):
            skipped += 1
            results.append(
                {
                    "ok": True,
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "template_name": _feedback_meta_name_for_template(db, tpl),
                    "outcome": "skipped",
                    "message": "Already in sync on selected profile",
                }
            )
            continue
        try:
            result = push_feedback_template_to_telnyx(
                db,
                tpl,
                remote_items=remote_items,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                force_push=force_push,
            )
            pushed += 1
            if result.get("skipped_push") or result.get("linked"):
                linked += 1
            results.append(
                {
                    "ok": True,
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "template_name": result.get("meta_name") or tpl.template_key,
                    "language": tpl.language,
                    "message": result.get("message"),
                    "linked": bool(result.get("linked")),
                    "outcome": "content_updated" if not result.get("linked") else "linked",
                }
            )
        except FeedbackTelnyxPushError as exc:
            failed += 1
            err = {
                "template_id": tpl.id,
                "template_key": tpl.template_key,
                "template_name": _feedback_meta_name_for_template(db, tpl),
                "language": tpl.language,
                "error": str(exc),
            }
            errors.append(err)
            results.append({"ok": False, **err, "outcome": "failed"})

    has_more = start + len(slice_rows) < total
    next_offset = start + len(slice_rows)
    db.commit()
    return {
        "ok": failed == 0,
        "total": total,
        "processed": next_offset,
        "offset": start,
        "limit": batch_limit,
        "has_more": has_more,
        "next_offset": next_offset,
        "pushed": pushed,
        "linked": linked,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "results": results,
        "content_updated": pushed - linked,
        "error_count": failed,
        "connection_profile_id": connection_profile_id,
        "force_push": force_push,
        "industry_id": industry.id if industry else None,
        "message": (
            f"{'Mirrored' if force_push else 'Pushed'} batch {start + 1}–{next_offset} of {total} "
            f"for {scope_label}"
            + (f" ({skipped} unchanged skipped)" if skipped else "")
            + (f", {failed} failed" if failed else "")
        ),
    }


def push_feedback_templates_batch(
    db: Session,
    *,
    industry_id: str,
    offset: int = 0,
    limit: int = 10,
    dry_run: bool = False,
    phase: str = "push",
    connection_profile_id: str | None = None,
    force_push: bool = False,
    service_code: str = "customer_feedback",
) -> dict[str, Any]:
    """Batched industry sync — push slice or pull statuses (mirrors WA Survey push-all)."""
    industry = resolve_feedback_industry(db, industry_id=industry_id)
    phase_norm = str(phase or "push").strip().lower()

    if phase_norm == "pull":
        refresh = refresh_feedback_template_status_from_telnyx_for_industry(
            db,
            industry_id=industry.id,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        return {
            "ok": True,
            "phase": "pull",
            "industry_id": industry.id,
            "industry_name": industry.name,
            "pull": refresh,
            "has_more": False,
            "total": int(refresh.get("template_count") or 0),
            "processed": int(refresh.get("matched") or 0),
            "message": str(refresh.get("message") or "Status refresh complete"),
        }

    if force_push and not dry_run:
        return push_feedback_platform_batch(
            db,
            offset=offset,
            limit=limit,
            force_push=True,
            connection_profile_id=connection_profile_id,
            industry_id=industry.id,
            service_code=service_code,
        )

    templates = list_feedback_templates_for_industry(db, industry.id)
    total = len(templates)
    if total == 0:
        return {
            "ok": True,
            "phase": "push",
            "industry_id": industry.id,
            "industry_name": industry.name,
            "total": 0,
            "processed": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
            "next_offset": 0,
            "pushed": 0,
            "linked": 0,
            "failed": 0,
            "errors": [],
            "results": [],
            "message": f"No templates found for industry {industry.name!r}.",
        }

    start = max(0, int(offset or 0))
    batch_limit = max(1, min(int(limit or 10), 50))
    slice_rows = templates[start : start + batch_limit]

    remote_items: list[dict[str, Any]] | None = None
    if not dry_run and slice_rows:
        try:
            remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                allow_account_waba_fallback=not bool(connection_profile_id),
            )
        except Exception as exc:
            logger.warning("feedback_telnyx_batch_prefetch_failed: %s", str(exc)[:200])
            remote_items = []

    batch: list[FeedbackWaTemplate] = []
    skipped = 0
    for tpl in slice_rows:
        if dry_run or force_push or _feedback_template_needs_push(db, tpl, remote_items or []):
            batch.append(tpl)
        else:
            skipped += 1

    has_more = start + len(slice_rows) < total
    next_offset = start + len(slice_rows)

    pushed = 0
    linked = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for tpl in batch:
        try:
            result = push_feedback_template_to_telnyx(
                db,
                tpl,
                dry_run=dry_run,
                remote_items=remote_items,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                force_push=force_push,
            )
            pushed += 1
            if result.get("skipped_push") or result.get("linked"):
                linked += 1
            results.append(
                {
                    "ok": True,
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "template_name": result.get("meta_name") or tpl.template_key,
                    "meta_name": result.get("meta_name"),
                    "language": tpl.language,
                    "message": result.get("message"),
                    "linked": bool(result.get("linked")),
                    "outcome": "content_updated",
                }
            )
        except FeedbackTelnyxPushError as exc:
            failed += 1
            err = {
                "template_id": tpl.id,
                "template_key": tpl.template_key,
                "template_name": tpl.template_key,
                "language": tpl.language,
                "error": str(exc),
            }
            errors.append(err)
            results.append({"ok": False, **err, "outcome": "failed"})

    db.commit()
    return {
        "ok": failed == 0,
        "phase": "push",
        "industry_id": industry.id,
        "industry_slug": industry.slug,
        "industry_name": industry.name,
        "total": total,
        "processed": next_offset,
        "offset": start,
        "limit": batch_limit,
        "has_more": has_more,
        "next_offset": next_offset,
        "pushed": pushed,
        "linked": linked,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "errors": errors,
        "results": results,
        "content_updated": pushed - linked,
        "error_count": failed,
        "message": (
            f"{'Validated' if dry_run else 'Pushed'} batch {start + 1}–{next_offset} of {total} "
            f"for {industry.name}"
            + (f" ({skipped} unchanged skipped)" if skipped else "")
            + (f", {failed} failed" if failed else "")
        ),
    }


def push_all_feedback_templates_for_survey_type(
    db: Session,
    *,
    survey_type_id: str,
    dry_run: bool = False,
    connection_profile_id: str | None = None,
    service_code: str = "customer_feedback",
    force_push: bool = False,
) -> dict[str, Any]:
    """Push all language variants for one feedback survey topic."""
    rows = list(
        db.execute(
            select(FeedbackWaTemplate)
            .where(FeedbackWaTemplate.survey_type_id == survey_type_id)
            .order_by(FeedbackWaTemplate.language)
        ).scalars().all()
    )
    if not rows:
        return {"ok": True, "pushed": 0, "failed": 0, "results": [], "message": "No templates for topic"}

    remote_items: list[dict[str, Any]] | None = None
    if not dry_run:
        try:
            remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                allow_account_waba_fallback=not bool(connection_profile_id),
            )
        except Exception as exc:
            logger.warning("feedback_topic_push_prefetch_failed: %s", str(exc)[:200])
            remote_items = []

    pushed = 0
    failed = 0
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for tpl in rows:
        try:
            result = push_feedback_template_to_telnyx(
                db,
                tpl,
                dry_run=dry_run,
                remote_items=remote_items,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                force_push=force_push,
            )
            pushed += 1
            results.append({"ok": True, "template_id": tpl.id, "language": tpl.language, **result})
        except FeedbackTelnyxPushError as exc:
            failed += 1
            errors.append({"template_id": tpl.id, "language": tpl.language, "error": str(exc)})
            results.append({"ok": False, "template_id": tpl.id, "error": str(exc)})

    db.commit()
    return {
        "ok": failed == 0,
        "pushed": pushed,
        "failed": failed,
        "results": results,
        "errors": errors,
        "message": f"Pushed {pushed}/{len(rows)} language variant(s)" + (f", {failed} failed" if failed else ""),
    }


def _feedback_template_meta_context(db: Session, tpl: FeedbackWaTemplate) -> tuple[str | None, str | None]:
    industry_slug: str | None = None
    survey_slug: str | None = None
    if tpl.industry_id:
        ind = db.get(FeedbackIndustry, tpl.industry_id)
        industry_slug = ind.slug if ind else None
    if tpl.survey_type_id:
        st = db.get(FeedbackSurveyType, tpl.survey_type_id)
        survey_slug = st.slug if st else None
        if not industry_slug and st:
            ind = db.get(FeedbackIndustry, st.industry_id)
            industry_slug = ind.slug if ind else None
    return industry_slug, survey_slug


def refresh_feedback_template_status_from_telnyx_for_industry(
    db: Session,
    *,
    industry_id: str | None = None,
    industry_slug: str | None = None,
    connection_profile_id: str | None = None,
    service_code: str = "customer_feedback",
) -> dict[str, Any]:
    """Pull Meta/Telnyx approval status for all templates in an industry."""
    industry = resolve_feedback_industry(db, industry_id=industry_id, industry_slug=industry_slug)
    templates = list_feedback_templates_for_industry(db, industry.id)
    if not templates:
        return {
            "ok": True,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "template_count": 0,
            "matched": 0,
            "updated": 0,
            "approved": 0,
            "pending": 0,
            "not_found": 0,
            "message": f"No templates found for industry {industry.name!r}.",
        }

    try:
        remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
            allow_account_waba_fallback=not bool(connection_profile_id),
        )
    except Exception as exc:
        raise FeedbackTelnyxPushError(f"Could not fetch templates from provider: {exc}") from exc

    matched = 0
    updated = 0
    approved = 0
    pending = 0
    not_found = 0
    results: list[dict[str, Any]] = []

    for tpl in templates:
        industry_slug_ctx, survey_slug_ctx = _feedback_template_meta_context(db, tpl)
        meta_name = feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug_ctx,
            survey_type_slug=survey_slug_ctx,
        )
        language = normalize_feedback_language(tpl.language)
        remote = find_remote_feedback_template(remote_items, name=meta_name, language=language)
        if remote is None:
            not_found += 1
            results.append(
                {
                    "template_id": tpl.id,
                    "template_key": tpl.template_key,
                    "meta_name": meta_name,
                    "language": language,
                    "matched": False,
                    "telnyx_sync_status": tpl.telnyx_sync_status,
                }
            )
            continue

        matched += 1
        previous = str(tpl.telnyx_sync_status or "")
        local_status = _apply_remote_status(db, tpl, remote)
        if local_status != previous:
            updated += 1
        if local_status == "approved":
            approved += 1
        elif local_status == "pending":
            pending += 1
        results.append(
            {
                "template_id": tpl.id,
                "template_key": tpl.template_key,
                "meta_name": meta_name,
                "language": language,
                "matched": True,
                "remote_status": str(remote.get("status") or ""),
                "telnyx_sync_status": local_status,
            }
        )

    db.commit()
    return {
        "ok": True,
        "industry_id": industry.id,
        "industry_slug": industry.slug,
        "industry_name": industry.name,
        "template_count": len(templates),
        "matched": matched,
        "updated": updated,
        "approved": approved,
        "pending": pending,
        "not_found": not_found,
        "results": results,
        "message": (
            f"Refreshed {matched}/{len(templates)} template(s) for {industry.name}"
            + (f" — {approved} approved" if approved else "")
            + (f", {pending} pending" if pending else "")
            + (f", {not_found} not on Meta yet" if not_found else "")
        ),
    }


def refresh_feedback_platform_status(
    db: Session,
    *,
    connection_profile_id: str | None = None,
    service_code: str = "customer_feedback",
) -> dict[str, Any]:
    """Pull approval status for all active customer feedback templates (hub refresh)."""
    industries = list(
        db.execute(
            select(FeedbackIndustry)
            .where(FeedbackIndustry.is_active.is_(True))
            .order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
        ).scalars().all()
    )
    total_templates = 0
    matched = 0
    updated = 0
    approved = 0
    pending = 0
    not_found = 0
    industry_results: list[dict[str, Any]] = []

    for industry in industries:
        refresh = refresh_feedback_template_status_from_telnyx_for_industry(
            db,
            industry_id=industry.id,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        industry_results.append(refresh)
        total_templates += int(refresh.get("template_count") or 0)
        matched += int(refresh.get("matched") or 0)
        updated += int(refresh.get("updated") or 0)
        approved += int(refresh.get("approved") or 0)
        pending += int(refresh.get("pending") or 0)
        not_found += int(refresh.get("not_found") or 0)

    return {
        "ok": True,
        "template_count": total_templates,
        "matched": matched,
        "updated": updated,
        "approved": approved,
        "pending": pending,
        "not_found": not_found,
        "industry_count": len(industries),
        "industries": industry_results,
        "connection_profile_id": connection_profile_id,
        "message": (
            f"Refreshed status for {matched}/{total_templates} customer feedback template(s)"
            + (f" — {updated} row(s) updated" if updated else "")
        ),
    }
