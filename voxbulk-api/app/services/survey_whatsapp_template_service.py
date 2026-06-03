"""Survey WhatsApp template library — clone, push, sync, preview."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_service import SurveyTypeService
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_whatsapp_template_sync_service import (
    TELNYX_WHATSAPP_TEMPLATES_URL,
    TelnyxWhatsappTemplateSyncService,
    _body_preview,
    _send_template_id_from_api_item,
    send_template_id_for_row,
    template_to_dict,
)
from app.services.telnyx_voice_service import _telnyx_config, _telnyx_headers, _telnyx_http_error_detail, TelnyxConfigError

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\{\{(\d+)\}\}")
_SURVEY_NAME_RE = re.compile(r"survey", re.I)
_LOCAL_ID_PREFIX = "local-"

ANONYMOUS_BODY_SENTENCE = "This survey is anonymous. Your name will not appear in the results."
ANONYMOUS_FOOTER = "Anonymous survey"

VARIANT_STANDARD = "standard"
VARIANT_ANONYMOUS = "anonymous"

SYNC_IN_SYNC = "in_sync"
SYNC_LOCAL_CHANGES = "local_changes"
SYNC_REMOTE_CHANGED = "remote_changed"
SYNC_ERROR = "error"
SYNC_DRAFT = "draft"


class SurveyWhatsappTemplateError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload


def _provider_error_payload(
    *,
    message: str,
    template_name: str | None = None,
    provider_error: str | None = None,
    status_code: int | None = None,
    telnyx_request_mode: str | None = None,
) -> dict[str, Any]:
    return {
        "message": message,
        "template_name": template_name,
        "provider_error": provider_error,
        "status_code": status_code,
        "telnyx_request_mode": telnyx_request_mode,
    }


def _validate_mobile_number(raw: str) -> tuple[str | None, str | None]:
    from app.services.telnyx_api_key import normalize_telnyx_e164

    text = str(raw or "").strip()
    if not text:
        return None, "Mobile number is required."
    try:
        normalized = normalize_telnyx_e164(text)
    except ValueError:
        return None, "Enter a valid mobile number in E.164 format (e.g. +447700900123)."
    if not normalized:
        return None, "Enter a valid mobile number in E.164 format (e.g. +447700900123)."
    digits = normalized.lstrip("+")
    if len(digits) < 10 or len(digits) > 15:
        return None, "Mobile number must be 10–15 digits including country code (e.g. +447700900123)."
    return normalized, None


def format_sync_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Turn raw sync counters into an admin-friendly structured result."""
    imported = int(summary.get("imported") or 0)
    updated = int(summary.get("updated") or 0)
    skipped = int(summary.get("skipped") or 0)
    failed = int(summary.get("failed") or 0)
    remote_count = int(summary.get("remote_count") or 0)
    survey_matched = int(summary.get("survey_matched") or 0)
    linked = int(summary.get("linked_to_survey_type") or 0)
    unlinked = int(summary.get("unlinked_survey_templates") or 0)
    filter_desc = str(
        summary.get("filter_description")
        or "Template names must contain “survey” (case-insensitive) to import into WA Survey."
    )
    errors = summary.get("errors") or []
    provider_error = summary.get("provider_error")
    status_code = summary.get("status_code")

    success = bool(summary.get("ok", failed == 0 and not provider_error))
    severity = "ok"
    message = ""

    if provider_error:
        success = False
        severity = "error"
        code = f" ({status_code})" if status_code else ""
        message = f"Telnyx sync failed{code}: {provider_error}"
    elif remote_count == 0:
        severity = "warn"
        message = (
            "Sync completed, but Telnyx returned 0 WhatsApp templates for the configured WABA/account. "
            "Check Integrations → Telnyx → WhatsApp Business Account ID."
        )
    elif survey_matched == 0:
        severity = "warn"
        message = (
            f"Sync completed, but no survey templates were found in Telnyx for the current filter. "
            f"Telnyx returned {remote_count} template(s); {filter_desc}"
        )
    elif imported == 0 and updated == 0 and skipped == 0 and failed == 0:
        severity = "warn"
        message = (
            "Sync completed with no changes. "
            f"Matched {survey_matched} survey template(s) from {remote_count} remote template(s)."
        )
    elif failed > 0:
        severity = "warn" if imported + updated > 0 else "error"
        message = (
            f"Sync completed: {imported} imported, {updated} updated, {skipped} skipped, {failed} failed."
        )
        if errors:
            message += f" First error: {errors[0]}"
    else:
        message = f"Sync completed: {imported} imported, {updated} updated, {skipped} skipped, {failed} failed."
        if unlinked > 0:
            message += (
                f" {unlinked} survey template(s) are stored but not linked to a survey type "
                "(name must match voxbulk_survey_{{slug}}_standard|anonymous or open sync from a survey type edit page)."
            )
        elif linked > 0:
            message += f" Linked {linked} template(s) to the current survey type."

    return {
        **summary,
        "success": success,
        "severity": severity,
        "message": message,
        "filter_description": filter_desc,
        "counts": {
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "remote_count": remote_count,
            "survey_matched": survey_matched,
            "linked_to_survey_type": linked,
            "unlinked_survey_templates": unlinked,
        },
    }


def _now() -> datetime:
    return datetime.utcnow()


def _loads(raw: str | None) -> Any:
    try:
        return json.loads(raw or "null")
    except json.JSONDecodeError:
        return None


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _telnyx_name_for(survey_slug: str, variant: str) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", str(survey_slug or "survey").lower()).strip("_")
    var = re.sub(r"[^a-z0-9_]+", "_", str(variant or "standard").lower()).strip("_")
    return f"voxbulk_survey_{base}_{var}"[:128]


def _content_hash(components: list[Any] | None) -> str | None:
    if not isinstance(components, list):
        return None
    raw = json.dumps(components, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _extract_example_values(components: list[Any] | None) -> list[str]:
    if not isinstance(components, list):
        return []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BODY":
            continue
        example = comp.get("example")
        if isinstance(example, dict):
            body_text = example.get("body_text")
            if isinstance(body_text, list) and body_text and isinstance(body_text[0], list):
                return [str(v) for v in body_text[0]]
        break
    return []


def _default_standard_components(*, org_label: str = "Northgate Dental", first_name: str = "Alex") -> list[dict[str, Any]]:
    return [
        {
            "type": "BODY",
            "text": (
                f"Hi {{{{1}}}}, we'd love your feedback about {org_label}. "
                "Tap below to start a short survey — it only takes a minute."
            ),
            "example": {"body_text": [[first_name]]},
        },
        {
            "type": "FOOTER",
            "text": "Reply STOP to opt out",
        },
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}],
        },
    ]


def _apply_anonymous_wording(components: list[Any]) -> list[Any]:
    out: list[Any] = []
    body_done = False
    footer_done = False
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        cloned = dict(comp)
        if ctype == "BODY":
            text = str(cloned.get("text") or "")
            if ANONYMOUS_BODY_SENTENCE.lower() not in text.lower():
                text = f"{text.rstrip()}\n\n{ANONYMOUS_BODY_SENTENCE}".strip()
            cloned["text"] = text
            body_done = True
        if ctype == "FOOTER":
            cloned["text"] = ANONYMOUS_FOOTER
            footer_done = True
        out.append(cloned)
    if not body_done:
        out.insert(
            0,
            {
                "type": "BODY",
                "text": ANONYMOUS_BODY_SENTENCE,
                "example": {"body_text": [["there"]]},
            },
        )
    if not footer_done:
        out.append({"type": "FOOTER", "text": ANONYMOUS_FOOTER})
    return out


def _render_body_text(text: str, values: list[str]) -> str:
    out = str(text or "")
    for idx, value in enumerate(values, start=1):
        out = out.replace(f"{{{{{idx}}}}}", str(value))
    return out


def _buttons_from_components(components: list[Any] | None) -> list[dict[str, Any]]:
    if not isinstance(components, list):
        return []
    for comp in components:
        if not isinstance(comp, dict) or str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        buttons = comp.get("buttons")
        if not isinstance(buttons, list):
            return []
        out: list[dict[str, Any]] = []
        for btn in buttons:
            if not isinstance(btn, dict):
                continue
            out.append(
                {
                    "label": str(btn.get("text") or btn.get("title") or "Button"),
                    "type": str(btn.get("type") or "QUICK_REPLY").lower(),
                }
            )
        return out
    return []


def _effective_components(row: TelnyxWhatsappTemplate) -> list[Any]:
    draft = _loads(row.draft_components_json)
    if isinstance(draft, list) and draft:
        return draft
    remote = _loads(row.components_json)
    return remote if isinstance(remote, list) else []


def _is_local_row(row: TelnyxWhatsappTemplate) -> bool:
    rid = str(row.telnyx_record_id or "")
    return rid.startswith(_LOCAL_ID_PREFIX) or str(row.status or "").upper() == "LOCAL_DRAFT"


def _refresh_local_sync_status(row: TelnyxWhatsappTemplate) -> str:
    draft = _loads(row.draft_components_json)
    remote = _loads(row.components_json)
    if _is_local_row(row):
        return SYNC_DRAFT if isinstance(draft, list) and draft else SYNC_LOCAL_CHANGES
    draft_hash = _content_hash(draft if isinstance(draft, list) else None)
    remote_hash = row.remote_content_hash or _content_hash(remote if isinstance(remote, list) else None)
    if draft_hash and remote_hash and draft_hash != remote_hash:
        return SYNC_LOCAL_CHANGES
    if remote_hash and row.remote_content_hash and remote_hash != row.remote_content_hash:
        return SYNC_REMOTE_CHANGED
    if row.last_push_error:
        return SYNC_ERROR
    return SYNC_IN_SYNC


def survey_template_to_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    base = template_to_dict(row)
    components = _effective_components(row)
    sync_status = _refresh_local_sync_status(row)
    row.local_sync_status = sync_status
    examples = _loads(row.example_values_json)
    if not isinstance(examples, list):
        examples = _extract_example_values(components)
    return {
        **base,
        "display_name": row.display_name or row.name,
        "survey_type_id": row.survey_type_id,
        "variant_type": row.variant_type or VARIANT_STANDARD,
        "parent_template_id": row.parent_template_id,
        "approval_status": str(row.status or "UNKNOWN").upper(),
        "sync_status": sync_status,
        "sync_status_label": sync_status.replace("_", " ").title(),
        "active_for_survey": bool(row.active_for_survey),
        "example_values": examples,
        "draft_components": _loads(row.draft_components_json),
        "remote_components": _loads(row.components_json),
        "buttons": _buttons_from_components(components),
        "footer": next(
            (
                str(c.get("text") or "")
                for c in components
                if isinstance(c, dict) and str(c.get("type") or "").upper() == "FOOTER"
            ),
            "",
        ),
        "last_pushed_at": row.last_pushed_at.isoformat() if row.last_pushed_at else None,
        "last_push_error": row.last_push_error,
        "is_local_only": _is_local_row(row),
        "send_template_id": send_template_id_for_row(row),
    }


class SurveyWhatsappTemplateService:
    @staticmethod
    def list_for_survey_type(db: Session, survey_type_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.survey_type_id == survey_type_id)
                .order_by(TelnyxWhatsappTemplate.variant_type.asc(), TelnyxWhatsappTemplate.name.asc())
            ).scalars().all()
        )
        return [survey_template_to_dict(row) for row in rows]

    @staticmethod
    def get_template(db: Session, template_id: int) -> TelnyxWhatsappTemplate | None:
        try:
            tid = int(template_id)
        except (TypeError, ValueError):
            return None
        return db.get(TelnyxWhatsappTemplate, tid)

    @staticmethod
    def create_standard_draft(
        db: Session,
        *,
        survey_type: SurveyType,
        language: str = "en_US",
        category: str = "MARKETING",
    ) -> TelnyxWhatsappTemplate:
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        components = _default_standard_components()
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=_telnyx_name_for(survey_type.slug, VARIANT_STANDARD),
            display_name=f"{survey_type.name} — Standard",
            language=str(language or "en_US"),
            category=category,
            status="LOCAL_DRAFT",
            survey_type_id=survey_type.id,
            variant_type=VARIANT_STANDARD,
            body_preview=_body_preview(components),
            draft_components_json=_dumps(components),
            example_values_json=_dumps(_extract_example_values(components)),
            local_sync_status=SYNC_DRAFT,
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def save_draft(db: Session, row: TelnyxWhatsappTemplate, payload: dict[str, Any]) -> TelnyxWhatsappTemplate:
        if "display_name" in payload:
            row.display_name = str(payload.get("display_name") or row.display_name or row.name).strip() or row.name
        if "language" in payload and str(payload.get("language") or "").strip():
            row.language = str(payload["language"]).strip()
        if "category" in payload:
            row.category = str(payload.get("category") or row.category or "MARKETING").strip() or "MARKETING"
        if "active_for_survey" in payload:
            row.active_for_survey = bool(payload["active_for_survey"])
        components = payload.get("components")
        if isinstance(components, list):
            row.draft_components_json = _dumps(components)
            row.body_preview = _body_preview(components)
            row.example_values_json = _dumps(_extract_example_values(components))
        examples = payload.get("example_values")
        if isinstance(examples, list):
            row.example_values_json = _dumps([str(v) for v in examples])
        row.local_sync_status = _refresh_local_sync_status(row)
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def clone_as_anonymous(db: Session, parent: TelnyxWhatsappTemplate) -> TelnyxWhatsappTemplate:
        if parent.survey_type_id is None:
            raise SurveyWhatsappTemplateError("Parent template is not linked to a survey type")
        survey_type = db.get(SurveyType, parent.survey_type_id)
        if survey_type is None:
            raise SurveyWhatsappTemplateError("Survey type not found")
        if not survey_type.supports_anonymous:
            raise SurveyWhatsappTemplateError("Anonymous variants are disabled for this survey type")
        parent_components = _effective_components(parent)
        anon_components = _apply_anonymous_wording(parent_components)
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=_telnyx_name_for(survey_type.slug, VARIANT_ANONYMOUS),
            display_name=f"{survey_type.name} — Anonymous",
            language=parent.language,
            category=parent.category,
            status="LOCAL_DRAFT",
            survey_type_id=survey_type.id,
            variant_type=VARIANT_ANONYMOUS,
            parent_template_id=parent.id,
            body_preview=_body_preview(anon_components),
            draft_components_json=_dumps(anon_components),
            example_values_json=_dumps(_extract_example_values(anon_components)),
            local_sync_status=SYNC_DRAFT,
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "survey_wa_template_cloned_anonymous",
            extra={"parent_id": parent.id, "new_id": row.id, "survey_type_id": survey_type.id},
        )
        return row

    @staticmethod
    def _telnyx_config(db: Session) -> dict[str, Any]:
        try:
            return _telnyx_config(db)
        except TelnyxConfigError as e:
            raise SurveyWhatsappTemplateError(str(e)) from e

    @staticmethod
    def push_to_telnyx(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        components = _effective_components(row)
        if not components:
            raise SurveyWhatsappTemplateError("Template has no components to push")

        config = SurveyWhatsappTemplateService._telnyx_config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)
        waba_id = str(config.get("whatsapp_waba_id") or config.get("waba_id") or "").strip()
        if not waba_id:
            raise SurveyWhatsappTemplateError("WhatsApp Business Account ID is not configured in Telnyx settings")

        approval = str(row.status or "").upper()
        if approval == "APPROVED" and not _is_local_row(row):
            remote_hash = row.remote_content_hash
            draft_hash = _content_hash(components)
            if remote_hash and draft_hash and remote_hash != draft_hash:
                raise SurveyWhatsappTemplateError(
                    "This template is APPROVED on Meta. Content changes require a new template submission — "
                    "clone this template or create a new variant, then Push to Telnyx."
                )

        payload = {
            "name": str(row.name or "").strip(),
            "category": str(row.category or "MARKETING").upper(),
            "language": str(row.language or "en_US"),
            "waba_id": waba_id,
            "components": components,
        }
        logger.info(
            "survey_wa_template_push_start",
            extra={"template_id": row.id, "template_name": row.name, "variant": row.variant_type},
        )
        try:
            with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
                response = client.post(
                    TELNYX_WHATSAPP_TEMPLATES_URL,
                    headers=_telnyx_headers(api_key),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as e:
            detail = _telnyx_http_error_detail(e)
            row.last_push_error = detail
            row.local_sync_status = SYNC_ERROR
            row.updated_at = _now()
            db.add(row)
            db.commit()
            logger.warning("survey_wa_template_push_failed", extra={"template_id": row.id, "error": detail})
            raise SurveyWhatsappTemplateError(
                f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                payload=_provider_error_payload(
                    message=f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                    template_name=row.name,
                    provider_error=detail,
                    status_code=e.response.status_code if e.response is not None else None,
                    telnyx_request_mode="create_or_update_template",
                ),
            ) from e
        except Exception as e:
            row.last_push_error = str(e)
            row.local_sync_status = SYNC_ERROR
            row.updated_at = _now()
            db.add(row)
            db.commit()
            raise SurveyWhatsappTemplateError(str(e)) from e

        item = body.get("data") if isinstance(body, dict) else None
        if not isinstance(item, dict):
            raise SurveyWhatsappTemplateError("Telnyx returned an unexpected response")

        record_id = str(item.get("id") or "").strip()
        send_id = _send_template_id_from_api_item(item)
        row.telnyx_record_id = record_id or send_id
        row.template_id = send_id
        row.status = str(item.get("status") or "PENDING").upper()
        row.components_json = _dumps(item.get("components") or components)
        row.draft_components_json = row.components_json
        row.remote_content_hash = _content_hash(_loads(row.components_json))
        row.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
        row.last_pushed_at = _now()
        row.last_push_error = None
        row.local_sync_status = SYNC_IN_SYNC
        row.synced_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "survey_wa_template_push_ok",
            extra={"template_id": row.id, "telnyx_record_id": row.telnyx_record_id, "status": row.status},
        )
        tpl = survey_template_to_dict(row)
        return {
            "ok": True,
            "success": True,
            "message": f"Pushed “{tpl.get('display_name') or row.name}” to Telnyx — status {row.status}.",
            "template": tpl,
            "template_name": row.name,
            "approval_status": str(row.status or "").upper(),
            "telnyx_request_mode": "create_or_update_template",
        }

    @staticmethod
    def _link_template_to_survey_type(
        db: Session,
        row: TelnyxWhatsappTemplate,
        name: str,
        survey_type_id: str | None,
    ) -> bool:
        if row.survey_type_id is not None:
            return False
        slug_match = re.search(r"voxbulk_survey_([a-z0-9_]+)_(standard|anonymous)", name.lower())
        if slug_match:
            st = SurveyTypeService.get_by_slug(db, slug_match.group(1))
            if st is not None:
                row.survey_type_id = st.id
                row.variant_type = slug_match.group(2)
                return True
        scoped = str(survey_type_id or "").strip()
        if not scoped:
            return False
        survey_type = db.get(SurveyType, scoped)
        if survey_type is None:
            return False
        slug = str(survey_type.slug or "").lower()
        lowered = name.lower()
        if slug and slug in lowered:
            row.survey_type_id = survey_type.id
            if "anonymous" in lowered:
                row.variant_type = VARIANT_ANONYMOUS
            elif not row.variant_type:
                row.variant_type = VARIANT_STANDARD
            return True
        return False

    @staticmethod
    def sync_from_telnyx(db: Session, *, survey_type_id: str | None = None) -> dict[str, Any]:
        logger.info("survey_wa_template_sync_start", extra={"survey_type_id": survey_type_id})
        filter_description = (
            "Only Telnyx templates whose names contain “survey” are imported into the WA Survey library."
        )
        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db)
        except Exception as exc:
            from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncError

            provider_error = str(exc)
            status_code = None
            if isinstance(exc, TelnyxWhatsappTemplateSyncError) and "401" in provider_error:
                status_code = 401
            summary = format_sync_summary(
                {
                    "ok": False,
                    "imported": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "remote_count": 0,
                    "survey_matched": 0,
                    "linked_to_survey_type": 0,
                    "unlinked_survey_templates": 0,
                    "provider_error": provider_error,
                    "status_code": status_code,
                    "filter_description": filter_description,
                    "errors": [provider_error],
                }
            )
            logger.warning("survey_wa_template_sync_failed", extra={"error": provider_error})
            return summary

        matched = [item for item in remote if _SURVEY_NAME_RE.search(str(item.get("name") or ""))]
        logger.info(
            "survey_wa_template_sync_fetched",
            extra={"remote_count": len(remote), "survey_matched": len(matched)},
        )

        imported = updated = skipped = failed = linked = 0
        errors: list[str] = []
        now = _now()
        scoped_type_id = str(survey_type_id or "").strip() or None

        for item in matched:
            try:
                record_id = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                if not record_id or not name:
                    skipped += 1
                    continue
                status = str(item.get("status") or "UNKNOWN").strip().upper()
                if status in {"DELETED", "DISABLED", "PENDING_DELETION"}:
                    existing = db.execute(
                        select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
                    ).scalar_one_or_none()
                    if existing is not None:
                        db.delete(existing)
                    skipped += 1
                    continue

                components = item.get("components")
                components_json = _dumps(components) if components is not None else None
                remote_hash = _content_hash(components if isinstance(components, list) else None)
                send_id = _send_template_id_from_api_item(item)

                existing = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
                ).scalar_one_or_none()
                is_new = existing is None
                if existing is None:
                    existing = TelnyxWhatsappTemplate(
                        telnyx_record_id=record_id,
                        template_id=send_id,
                        name=name,
                        language=str(item.get("language") or "en_US"),
                        created_at=now,
                    )
                    db.add(existing)
                    imported += 1
                else:
                    updated += 1

                existing.template_id = send_id
                existing.name = name
                existing.language = str(item.get("language") or "en_US")
                existing.category = str(item.get("category") or "").strip() or None
                existing.status = status
                existing.components_json = components_json
                existing.body_preview = _body_preview(components if isinstance(components, list) else None)
                existing.example_values_json = _dumps(_extract_example_values(components if isinstance(components, list) else None))
                existing.remote_content_hash = remote_hash
                existing.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
                existing.synced_at = now
                existing.updated_at = now

                if "anonymous" in name.lower():
                    existing.variant_type = VARIANT_ANONYMOUS
                elif not existing.variant_type:
                    existing.variant_type = VARIANT_STANDARD

                if SurveyWhatsappTemplateService._link_template_to_survey_type(db, existing, name, scoped_type_id):
                    linked += 1
                elif existing.survey_type_id is None:
                    SurveyWhatsappTemplateService._link_template_to_survey_type(db, existing, name, None)

                draft_hash = _content_hash(_loads(existing.draft_components_json))
                if draft_hash and remote_hash and draft_hash != remote_hash:
                    existing.local_sync_status = SYNC_REMOTE_CHANGED
                else:
                    existing.draft_components_json = components_json
                    existing.local_sync_status = SYNC_IN_SYNC
            except Exception as exc:
                failed += 1
                err = f"template parsing error for {item.get('name') or 'unknown'}: {exc}"
                errors.append(err)
                logger.exception("survey_wa_template_sync_item_failed", extra={"template_name": item.get("name")})

        db.commit()

        unlinked = db.execute(
            select(func.count())
            .select_from(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.survey_type_id.is_(None),
                TelnyxWhatsappTemplate.name.ilike("%survey%"),
            )
        ).scalar_one()

        raw_summary = {
            "ok": failed == 0,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "remote_count": len(remote),
            "survey_matched": len(matched),
            "linked_to_survey_type": linked,
            "unlinked_survey_templates": int(unlinked or 0),
            "filter_description": filter_description,
            "errors": errors[:20],
        }
        summary = format_sync_summary(raw_summary)
        logger.info("survey_wa_template_sync_end", extra=summary.get("counts", raw_summary))
        return summary

    @staticmethod
    def _messaging_org_id(db: Session) -> str:
        from sqlalchemy import select as sa_select

        from app.models.organisation import Organisation
        from app.services.provider_settings import ProviderSettingsService

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        config = cfg if isinstance(cfg, dict) else {}
        org_id = str(config.get("messaging_org_id") or config.get("default_messaging_org_id") or "").strip()
        if org_id:
            return org_id
        fallback = db.execute(sa_select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
        return str(fallback or "")

    @staticmethod
    def send_test_template(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        to_number: str,
        first_name: str = "Alex",
        business_name: str = "Northgate Dental",
    ) -> dict[str, Any]:
        from app.services.telnyx_messaging_service import TelnyxMessagingService

        template_label = str(row.display_name or row.name or "template")
        approval = str(row.status or "").upper()
        if _is_local_row(row):
            raise SurveyWhatsappTemplateError(
                f"Template “{template_label}” is a local draft only. Save Draft, Push to Telnyx, and wait for Meta approval before sending a test."
            )
        if approval != "APPROVED":
            raise SurveyWhatsappTemplateError(
                f"Template “{template_label}” is not APPROVED (status: {approval or 'UNKNOWN'}). "
                "Push to Telnyx and wait for Meta approval before sending a test."
            )

        recipient, phone_error = _validate_mobile_number(to_number)
        if phone_error:
            raise SurveyWhatsappTemplateError(phone_error)

        preview = SurveyWhatsappTemplateService.build_preview(
            db,
            row,
            business_name=business_name,
            first_name=first_name,
        )
        examples = preview.get("example_values") or [first_name]
        first = str(examples[0] if examples else first_name)
        template_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={
                "first_name": first,
                "clinic_name": business_name,
                "organisation_name": business_name,
            },
        )
        send_id = send_template_id_for_row(row)
        org_id = SurveyWhatsappTemplateService._messaging_org_id(db)

        langs: list[str] = []
        for candidate in (row.language, "en_US", "en_GB", "en"):
            code = str(candidate or "").strip()
            if code and code not in langs:
                langs.append(code)
        if not langs:
            langs = ["en_US"]

        result = None
        telnyx_request_mode = "template_name"
        for lang in langs:
            attempt = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=recipient,
                body=str(preview.get("rendered_body") or row.body_preview or "Survey test"),
                template_name=row.name,
                template_language=lang,
                template_components=template_components,
                org_id=org_id or None,
                meter_usage=False,
            )
            result = attempt
            if attempt.ok:
                telnyx_request_mode = f"template_name:{lang}"
                break

        if (result is None or not result.ok) and send_id:
            telnyx_request_mode = "template_id"
            for lang in langs:
                attempt = TelnyxMessagingService.send_whatsapp(
                    db,
                    to_number=recipient,
                    body=str(preview.get("rendered_body") or row.body_preview or "Survey test"),
                    template_id=send_id,
                    template_language=lang,
                    template_components=template_components,
                    org_id=org_id or None,
                    meter_usage=False,
                )
                result = attempt
                if attempt.ok:
                    telnyx_request_mode = f"template_id:{lang}"
                    break

        if result is None or not result.ok:
            provider_error = (result.detail if result else None) or (result.status if result else "send_failed")
            raise SurveyWhatsappTemplateError(
                f"Telnyx test send failed for “{template_label}”.",
                payload=_provider_error_payload(
                    message=f"Telnyx test send failed for “{template_label}”.",
                    template_name=row.name,
                    provider_error=str(provider_error),
                    telnyx_request_mode=telnyx_request_mode,
                ),
            )

        return {
            "ok": True,
            "success": True,
            "message": f"Test survey sent to {recipient} using template “{row.name}”.",
            "to_number": recipient,
            "template_name": row.name,
            "template_id": send_id,
            "display_name": template_label,
            "approval_status": approval,
            "telnyx_request_mode": telnyx_request_mode,
            "external_id": result.external_id,
            "provider_status": result.status,
            "example_values": examples,
            "rendered_body_preview": str(preview.get("rendered_body") or "")[:240],
        }

    @staticmethod
    def resolve_for_survey(
        db: Session,
        *,
        survey_type_id: str,
        variant: str,
        language: str | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        variant_key = str(variant or VARIANT_STANDARD).strip().lower()
        q = (
            select(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.survey_type_id == survey_type_id,
                TelnyxWhatsappTemplate.variant_type == variant_key,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.updated_at.desc())
        )
        rows = list(db.execute(q).scalars().all())
        lang = str(language or "").strip()
        approved = [r for r in rows if str(r.status or "").upper() == "APPROVED"]
        pool = approved or rows
        if lang:
            for row in pool:
                if str(row.language or "") == lang:
                    return row
        return pool[0] if pool else None

    @staticmethod
    def build_preview(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        business_name: str = "Your business",
        first_name: str = "Alex",
    ) -> dict[str, Any]:
        components = _effective_components(row)
        examples = _loads(row.example_values_json)
        if not isinstance(examples, list) or not examples:
            examples = _extract_example_values(components)
        if not examples:
            examples = [first_name]

        body_parts: list[str] = []
        footer = ""
        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = str(comp.get("type") or "").upper()
            if ctype == "HEADER":
                fmt = str(comp.get("format") or "TEXT").upper()
                if fmt == "TEXT":
                    body_parts.insert(0, _render_body_text(str(comp.get("text") or ""), examples))
            elif ctype == "BODY":
                body_parts.append(_render_body_text(str(comp.get("text") or ""), examples))
            elif ctype == "FOOTER":
                footer = str(comp.get("text") or "")

        rendered_body = "\n\n".join(p for p in body_parts if p).strip() or str(row.body_preview or "")
        buttons = _buttons_from_components(components)
        placeholders = sorted({int(m.group(1)) for m in _VAR_RE.finditer(rendered_body + " " + str(row.body_preview or ""))})
        return {
            "template": survey_template_to_dict(row),
            "business_name": business_name,
            "rendered_body": rendered_body,
            "raw_body": next(
                (str(c.get("text") or "") for c in components if isinstance(c, dict) and str(c.get("type") or "").upper() == "BODY"),
                row.body_preview or "",
            ),
            "footer": footer,
            "buttons": buttons,
            "example_values": examples,
            "placeholders": [f"{{{{{n}}}}}" for n in placeholders],
            "approval_status": str(row.status or "").upper(),
            "sync_status": _refresh_local_sync_status(row),
            "disclaimer": (
                "First message is the approved WhatsApp template. Following steps simulate the survey conversation "
                "after the recipient taps a button — not a native multi-screen WhatsApp template."
            ),
        }
