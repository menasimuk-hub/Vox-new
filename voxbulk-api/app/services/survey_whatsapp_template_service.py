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
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.sales_whatsapp_telnyx_service import (
    canonical_telnyx_name_for_sales_key,
    legacy_telnyx_names_for_sales_key,
    resolve_whatsapp_template_languages,
)
from app.services.survey_industry_scope import apply_industry_to_template, template_matches_survey_industry
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import (
    SurveyTypeTemplateError,
    SurveyTypeTemplateService,
    template_belongs_to_survey_type,
    template_name_survey_slug,
)
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_whatsapp_template_sync_service import (
    TELNYX_WHATSAPP_TEMPLATES_URL,
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
    _body_preview,
    _send_template_id_from_api_item,
    send_template_id_for_row,
    template_to_dict,
)
from app.services.telnyx_voice_service import (
    _telnyx_config,
    _telnyx_headers,
    _telnyx_http_error_detail,
    resolve_telnyx_whatsapp_waba_id,
    TelnyxConfigError,
)
from app.services.wa_template_meta_sync import (
    META_SUBCODE_CONTENT_ALREADY_EXISTS,
    default_wa_template_language,
    enrich_template_push_error_payload,
    normalize_wa_template_language,
    parse_meta_error_from_provider_detail,
    validate_wa_template_name,
)
from app.services.wa_template_privacy import (
    PRIVACY_MODE_OFF,
    PRIVACY_MODE_ON,
    normalize_privacy_mode,
    privacy_mode_to_variant,
    resolve_mapping_privacy_mode,
    resolve_row_privacy_mode,
)

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\{\{(\d+)\}\}")
_SURVEY_NAME_RE = re.compile(r"survey", re.I)
_LOCAL_ID_PREFIX = "local-"

ANONYMOUS_BODY_SENTENCE = "This survey is anonymous. Your name will not appear in the results."
ANONYMOUS_FOOTER = "Anonymous survey"
STANDARD_OPT_OUT_FOOTER = "Reply STOP to opt out"

META_FOOTER_MAX_CHARS = 60
META_HEADER_MAX_CHARS = 60
META_BODY_HARD_MAX_CHARS = 1024
META_BODY_SOFT_MAX_CHARS = 550
META_BUTTON_LABEL_MAX_CHARS = 25
META_QUICK_REPLY_MAX_BUTTONS = 3

VARIANT_STANDARD = "standard"
VARIANT_ANONYMOUS = "anonymous"

SYNC_IN_SYNC = "in_sync"
SYNC_LOCAL_CHANGES = "local_changes"
SYNC_REMOTE_CHANGED = "remote_changed"
SYNC_ERROR = "error"
SYNC_DRAFT = "draft"

WA_TEMPLATE_CATEGORIES = frozenset({"MARKETING", "UTILITY", "AUTHENTICATION"})

TELNYX_SYNC_NOT_SYNCED = "Not synced"
TELNYX_SYNC_SYNCING = "Syncing"
TELNYX_SYNC_SYNCED = "Synced to Telnyx"
TELNYX_SYNC_PENDING = "Pending approval"
TELNYX_SYNC_APPROVED = "Approved"
TELNYX_SYNC_REJECTED = "Rejected"
TELNYX_SYNC_FAILED = "Sync failed"
TELNYX_SYNC_OUT_OF_SYNC = "Out of sync"

LOCAL_STATUS_DRAFT = "Draft"
LOCAL_STATUS_SAVED = "Template saved"


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


def _sync_content_hash(components: list[Any] | None) -> str | None:
    """Hash template content for sync comparison (ignores Meta-only BODY examples)."""
    normalized = _normalize_draft_components(components if isinstance(components, list) else None)
    return _content_hash(normalized)


def _extract_example_values(components: list[Any] | None) -> list[str]:
    if not isinstance(components, list):
        return []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BODY":
            continue
        text = str(comp.get("text") or "")
        var_ids = _meta_var_ids_in_text(text)
        if not var_ids:
            return []
        example = comp.get("example")
        if isinstance(example, dict):
            body_text = example.get("body_text")
            if isinstance(body_text, list) and body_text and isinstance(body_text[0], list):
                return [str(v) for v in body_text[0][: max(var_ids)]]
        break
    return []


def _meta_var_ids_in_text(text: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"\{\{(\d+)\}\}", str(text or ""))]


def _meta_var_ids_in_components(components: list[Any] | None) -> list[int]:
    if not isinstance(components, list):
        return []
    chunks: list[str] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        comp_type = str(comp.get("type") or "").upper()
        if comp_type in {"BODY", "HEADER"}:
            chunks.append(str(comp.get("text") or ""))
    return _meta_var_ids_in_text(" ".join(chunks))


def validate_meta_variable_order(components: list[Any] | None) -> str | None:
    """Return an error message when Meta/Telnyx variable numbering rules are violated."""
    var_ids = _meta_var_ids_in_components(components)
    if not var_ids:
        return None
    expected = list(range(1, max(var_ids) + 1))
    unique_sorted = sorted(set(var_ids))
    if unique_sorted != expected:
        return (
            f"WhatsApp variables must be sequential from {{{{1}}}} to {{{{{max(expected)}}}}} "
            f"with no gaps — found {unique_sorted}."
        )
    if var_ids != expected:
        return (
            f"WhatsApp variables must appear in ascending order in the template body "
            f"(expected {expected}, found {var_ids}). Move {{{{4}}}} after {{{{3}}}}, etc."
        )
    examples = _extract_example_values(components)
    if len(examples) < max(var_ids):
        return f"Add at least {max(var_ids)} sample value(s) for the template variables."
    return None


_DEFAULT_META_EXAMPLES = ["Alex", "Northgate Dental", "https://example.com/s/abc", "Monday 9am"]
META_STATIC_BODY_SAMPLE = "Sample"


def _resolve_example_values(
    components: list[Any] | None,
    *,
    row: TelnyxWhatsappTemplate | None = None,
    override: list[str] | None = None,
) -> list[str]:
    var_ids = _meta_var_ids_in_components(components)
    if not var_ids:
        return []

    if isinstance(override, list) and override:
        examples = [str(v) for v in override if str(v).strip()]
    elif row is not None:
        loaded = _loads(row.example_values_json)
        examples = [str(v) for v in loaded] if isinstance(loaded, list) else []
    else:
        examples = []
    if not examples:
        examples = _extract_example_values(components)
    if not examples:
        examples = _pad_example_values([], max(var_ids))
    return examples[: max(var_ids)]


def build_meta_body_component(text: str, *, example_values: list[str] | None = None) -> dict[str, Any]:
    """Build a Meta/Telnyx-compatible BODY component (example required even without variables)."""
    body = str(text or "").strip()
    var_ids = _meta_var_ids_in_text(body)
    component: dict[str, Any] = {"type": "BODY", "text": body}
    if var_ids:
        examples = [str(v) for v in (example_values or []) if str(v).strip()]
        if not examples:
            examples = _pad_example_values([], max(var_ids))
        body_example = _pad_example_values(examples, max(var_ids))
    else:
        body_example = [META_STATIC_BODY_SAMPLE]
    component["example"] = {"body_text": [body_example]}
    return component


def _pad_example_values(examples: list[str], count: int) -> list[str]:
    values = list(examples)
    while len(values) < count:
        fallback = (
            _DEFAULT_META_EXAMPLES[len(values)]
            if len(values) < len(_DEFAULT_META_EXAMPLES)
            else f"Sample {len(values) + 1}"
        )
        values.append(fallback)
    return values[:count]


def _meta_example_is_valid(example: Any, *, field: str) -> bool:
    if not isinstance(example, dict):
        return False
    rows = example.get(field)
    if not isinstance(rows, list) or not rows:
        return False
    if field == "header_text":
        return any(str(v).strip() for v in rows)
    first = rows[0]
    if isinstance(first, list):
        return any(str(v).strip() for v in first)
    return any(str(v).strip() for v in rows)


def _normalize_draft_components(components: list[Any] | None) -> list[Any]:
    """Persist draft components without Meta-only static examples."""
    if not isinstance(components, list):
        return []
    out: list[Any] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        cloned = dict(comp)
        ctype = str(cloned.get("type") or "").upper()
        if ctype == "BODY":
            text = str(cloned.get("text") or "")
            if not _meta_var_ids_in_text(text):
                cloned.pop("example", None)
            elif not _meta_example_is_valid(cloned.get("example"), field="body_text"):
                cloned.pop("example", None)
        out.append(cloned)
    return out


def _example_values_for_storage(
    components: list[Any] | None,
    *,
    override: list[str] | None = None,
) -> list[str]:
    var_ids = _meta_var_ids_in_components(components)
    if not var_ids:
        return []
    if isinstance(override, list):
        values = [str(v) for v in override][: max(var_ids)]
    else:
        values = _extract_example_values(components)
    if len(values) < max(var_ids):
        values = _pad_example_values(values, max(var_ids))
    return values[: max(var_ids)]


def _body_placeholder_error(text: str) -> str | None:
    """Return a validation error when body placeholders are not Meta positional {{1}} style."""
    body = str(text or "")
    if "{{" not in body:
        return None
    var_ids = _meta_var_ids_in_text(body)
    for match in re.finditer(r"\{\{([^}]+)\}\}", body):
        inner = str(match.group(1) or "").strip()
        if not inner.isdigit():
            return (
                f"Body contains invalid placeholder {{{{{inner}}}}}. "
                "Use only positional variables like {{1}}, {{2}} — or remove all braces."
            )
    if not var_ids:
        return None
    expected = list(range(1, max(var_ids) + 1))
    unique = sorted(set(var_ids))
    if unique != expected:
        return f"Body variables must run {{1}}..{{{max(expected)}}} with no gaps — found {unique}."
    stripped = body.strip()
    if re.match(r"^\{\{\d+\}\}", stripped):
        return "WhatsApp variables cannot be at the start of the body text."
    if re.search(r"\{\{\d+\}\}\s*$", stripped):
        return "WhatsApp variables cannot be at the end of the body text."
    return None


def _build_meta_header_component(comp: dict[str, Any], *, examples: list[str]) -> dict[str, Any]:
    text = str(comp.get("text") or "").strip()
    header: dict[str, Any] = {
        "type": "HEADER",
        "format": str(comp.get("format") or "TEXT").upper(),
        "text": text,
    }
    var_ids = _meta_var_ids_in_text(text)
    if var_ids:
        header["example"] = {"header_text": _pad_example_values(examples, max(var_ids))}
    return header


def _build_meta_buttons_component(comp: dict[str, Any]) -> dict[str, Any]:
    buttons_in = comp.get("buttons") if isinstance(comp.get("buttons"), list) else []
    buttons_out: list[dict[str, Any]] = []
    for btn in buttons_in:
        if not isinstance(btn, dict):
            continue
        cloned = dict(btn)
        kind = str(cloned.get("type") or "").upper()
        if kind == "URL" and "{{" in str(cloned.get("url") or ""):
            if not isinstance(cloned.get("example"), list) or not cloned.get("example"):
                cloned["example"] = ["Sample"]
        buttons_out.append(cloned)
    return {"type": "BUTTONS", "buttons": buttons_out}


def ensure_meta_examples_on_components(
    components: list[Any] | None,
    example_values: list[str] | None = None,
    *,
    row: TelnyxWhatsappTemplate | None = None,
) -> list[Any]:
    """Rebuild Meta/Telnyx-compatible components with required example fields before push."""
    if not isinstance(components, list):
        return []
    examples = _resolve_example_values(components, row=row, override=example_values)
    out: list[Any] = []
    body_count = 0
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        if ctype == "BODY":
            body_count += 1
            text = str(comp.get("text") or "").strip()
            if not text:
                raise SurveyWhatsappTemplateError("Template BODY text is empty.")
            layout_error = _body_placeholder_error(text)
            if layout_error:
                raise SurveyWhatsappTemplateError(layout_error)
            var_ids = _meta_var_ids_in_text(text)
            body_examples = examples if var_ids else None
            out.append(build_meta_body_component(text, example_values=body_examples))
        elif ctype == "HEADER":
            out.append(_build_meta_header_component(comp, examples=examples))
        elif ctype == "BUTTONS":
            out.append(_build_meta_buttons_component(comp))
        else:
            out.append(dict(comp))
    if body_count != 1:
        raise SurveyWhatsappTemplateError("Template must contain exactly one BODY component.")
    return out


def _assert_meta_ready_components(components: list[Any] | None) -> None:
    """Raise when any BODY/HEADER component would fail Meta's example requirement."""
    if not isinstance(components, list):
        raise SurveyWhatsappTemplateError("Template has no components to push")
    body_seen = 0
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        if ctype == "BODY":
            body_seen += 1
            example = comp.get("example")
            if not isinstance(example, dict) or "body_text" not in example:
                raise SurveyWhatsappTemplateError(
                    "Internal error: BODY example missing after Meta preparation — contact support."
                )
            if not _meta_example_is_valid(example, field="body_text"):
                raise SurveyWhatsappTemplateError(
                    "Internal error: BODY example is invalid after Meta preparation — contact support."
                )
        elif ctype == "HEADER":
            text = str(comp.get("text") or "")
            if _meta_var_ids_in_text(text) and not _meta_example_is_valid(comp.get("example"), field="header_text"):
                raise SurveyWhatsappTemplateError(
                    "Template HEADER is missing Meta example values for its variables."
                )
    if body_seen != 1:
        raise SurveyWhatsappTemplateError("Template must contain exactly one BODY component.")


_QUESTION_DRAFT_BODIES: dict[str, str] = {
    "rating": "How would you rate your overall experience?",
    "yes_no": "Would you recommend us to a friend?",
    "helpfulness": "How helpful was our team today?",
    "abc_choice": "Which best describes your visit?",
    "reason": "What stood out most during your visit?",
    "final_feedback_text": "Is there anything else you would like to share?",
    "feeling_word": "How did your experience feel overall?",
    "follow_up": "Is there anything we should clarify?",
    "improvement": "What could we improve for next time?",
}


def _question_button_components(step_role: str) -> list[dict[str, Any]]:
    from app.services.survey_step_bank_service import normalize_step_role

    role = normalize_step_role(step_role)
    button_map: dict[str, list[dict[str, str]]] = {
        "rating": [
            {"type": "QUICK_REPLY", "text": "Poor"},
            {"type": "QUICK_REPLY", "text": "Okay"},
            {"type": "QUICK_REPLY", "text": "Excellent"},
        ],
        "yes_no": [
            {"type": "QUICK_REPLY", "text": "Yes"},
            {"type": "QUICK_REPLY", "text": "No"},
        ],
        "helpfulness": [
            {"type": "QUICK_REPLY", "text": "Very helpful"},
            {"type": "QUICK_REPLY", "text": "Partly helpful"},
            {"type": "QUICK_REPLY", "text": "Not helpful"},
        ],
        "abc_choice": [
            {"type": "QUICK_REPLY", "text": "Option A"},
            {"type": "QUICK_REPLY", "text": "Option B"},
            {"type": "QUICK_REPLY", "text": "Option C"},
        ],
        "feeling_word": [
            {"type": "QUICK_REPLY", "text": "Great"},
            {"type": "QUICK_REPLY", "text": "Okay"},
            {"type": "QUICK_REPLY", "text": "Poor"},
        ],
    }
    return button_map.get(role, [])


def _default_question_components(*, step_role: str) -> list[dict[str, Any]]:
    from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role

    role = normalize_step_role(step_role)
    if role not in MIDDLE_STEP_ROLES:
        role = "rating"
    body = _QUESTION_DRAFT_BODIES.get(role, "How was your experience?")
    components: list[dict[str, Any]] = [
        {"type": "BODY", "text": body},
        {"type": "FOOTER", "text": STANDARD_OPT_OUT_FOOTER},
    ]
    buttons = _question_button_components(role)
    if buttons:
        components.append({"type": "BUTTONS", "buttons": buttons})
    return components


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


def normalize_wa_template_category(raw: Any, *, required: bool = False) -> str | None:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        if required:
            raise SurveyWhatsappTemplateError(
                "Template Category is required before syncing to Telnyx.",
                payload={"message": "Template Category is required before syncing to Telnyx."},
            )
        return None
    cat = str(raw).strip().upper()
    if cat not in WA_TEMPLATE_CATEGORIES:
        raise SurveyWhatsappTemplateError(
            f"Invalid Template Category “{cat}”. Must be MARKETING, UTILITY, or AUTHENTICATION.",
            payload={
                "message": f"Invalid Template Category “{cat}”. Must be MARKETING, UTILITY, or AUTHENTICATION.",
            },
        )
    return cat


def telnyx_sync_ui_label(row: TelnyxWhatsappTemplate, *, syncing: bool = False) -> str:
    if syncing:
        return TELNYX_SYNC_SYNCING
    content_sync = _refresh_local_sync_status(row)
    if row.last_push_error and (_is_local_row(row) or str(row.local_sync_status or "") == SYNC_ERROR):
        return TELNYX_SYNC_FAILED
    if _is_local_row(row):
        return TELNYX_SYNC_NOT_SYNCED
    status = str(row.status or "").upper()
    if status == "PENDING":
        if content_sync == SYNC_LOCAL_CHANGES:
            return TELNYX_SYNC_OUT_OF_SYNC
        return TELNYX_SYNC_PENDING
    if content_sync == SYNC_LOCAL_CHANGES and not _is_local_row(row):
        return TELNYX_SYNC_OUT_OF_SYNC
    if status == "APPROVED":
        return TELNYX_SYNC_APPROVED
    if status == "REJECTED":
        return TELNYX_SYNC_REJECTED
    if status in {"PAUSED", "DISABLED"}:
        return status.title()
    return TELNYX_SYNC_SYNCED


def resolve_local_status(row: TelnyxWhatsappTemplate) -> str:
    components = _effective_components(row)
    if not components:
        return LOCAL_STATUS_DRAFT
    if str(row.status or "").upper() == "LOCAL_DRAFT" and _is_local_row(row):
        return LOCAL_STATUS_SAVED if row.updated_at else LOCAL_STATUS_DRAFT
    return LOCAL_STATUS_SAVED


def template_workflow_state(row: TelnyxWhatsappTemplate, *, syncing: bool = False) -> dict[str, Any]:
    content_sync = _refresh_local_sync_status(row)
    telnyx_label = telnyx_sync_ui_label(row, syncing=syncing)
    needs_resync = telnyx_label in {
        TELNYX_SYNC_NOT_SYNCED,
        TELNYX_SYNC_OUT_OF_SYNC,
        TELNYX_SYNC_FAILED,
        TELNYX_SYNC_REJECTED,
    }
    return {
        "local_status": resolve_local_status(row),
        "sync_status": telnyx_label,
        "telnyx_sync_label": telnyx_label,
        "telnyx_status": str(row.status or "UNKNOWN").upper(),
        "telnyx_template_id": row.telnyx_record_id if not _is_local_row(row) else None,
        "last_synced_at": row.last_pushed_at.isoformat() if row.last_pushed_at else None,
        "sync_error": row.last_push_error,
        "needs_resync": needs_resync,
        "content_sync_status": content_sync,
    }


def telnyx_sync_action_message(row: TelnyxWhatsappTemplate, *, ok: bool, linked: bool = False) -> str:
    if not ok:
        return TELNYX_SYNC_FAILED
    status = str(row.status or "").upper()
    if linked:
        if status == "APPROVED":
            return "Linked to existing Telnyx template — Approved on Meta."
        if status == "PENDING":
            return "Linked to existing Telnyx template — Pending Meta approval."
        if status == "REJECTED":
            return "Linked to existing Telnyx template — Rejected by Meta."
        return "Linked to existing Telnyx template — status refreshed."
    if status == "PENDING":
        return TELNYX_SYNC_PENDING
    if status == "APPROVED":
        return TELNYX_SYNC_APPROVED
    return TELNYX_SYNC_SYNCED


def _remote_name_candidates_for_row(row: TelnyxWhatsappTemplate) -> list[str]:
    names: list[str] = []
    for candidate in (row.name,):
        text = str(candidate or "").strip()
        if text:
            names.append(text)
    key = str(row.sales_template_key or "").strip()
    if key:
        canonical = canonical_telnyx_name_for_sales_key(key)
        if canonical:
            names.append(canonical)
        names.extend(legacy_telnyx_names_for_sales_key(key))
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        lowered = name.strip().lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            deduped.append(name.strip())
    return deduped


def prepare_components_for_telnyx_push(
    components: list[Any] | None,
    *,
    row: TelnyxWhatsappTemplate | None = None,
    example_values: list[str] | None = None,
) -> list[Any]:
    """Normalize and rebuild components so every Telnyx/Meta push includes a valid BODY example."""
    normalized = _normalize_draft_components(components if isinstance(components, list) else None)
    prepared = ensure_meta_examples_on_components(normalized, example_values, row=row)
    _assert_meta_ready_components(prepared)
    return prepared


def _body_component_from_prepared(components: list[Any] | None) -> dict[str, Any] | None:
    if not isinstance(components, list):
        return None
    for comp in components:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
            return comp
    return None


def _patch_remote_template_on_telnyx(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    components: list[Any],
    api_key: str,
    record_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    rid = str(record_id or row.telnyx_record_id or "").strip()
    if not rid or rid.startswith(_LOCAL_ID_PREFIX):
        return None, None
    try:
        with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
            response = client.patch(
                f"{TELNYX_WHATSAPP_TEMPLATES_URL}/{rid}",
                headers=_telnyx_headers(api_key),
                json={"components": components},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        detail = _telnyx_http_error_detail(exc)
        logger.warning(
            "survey_wa_template_patch_failed",
            extra={
                "template_id": row.id,
                "template_name": row.name,
                "telnyx_record_id": rid,
                "status_code": exc.response.status_code if exc.response is not None else None,
                "error": detail,
            },
        )
        return None, detail
    except Exception as exc:
        detail = str(exc)
        logger.warning(
            "survey_wa_template_patch_failed",
            extra={"template_id": row.id, "template_name": row.name, "telnyx_record_id": rid, "error": detail},
        )
        return None, detail

    item = body.get("data") if isinstance(body, dict) else None
    if not isinstance(item, dict):
        return None, "Telnyx returned an unexpected PATCH response"
    _apply_remote_telnyx_item(row, item, overwrite_draft=False)
    return _push_success_response(db, row, telnyx_request_mode="patch_template"), None


def _push_success_response(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    telnyx_request_mode: str,
    linked: bool = False,
) -> dict[str, Any]:
    row.last_pushed_at = _now()
    row.last_push_error = None
    row.local_sync_status = _refresh_local_sync_status(row)
    row.synced_at = _now()
    row.updated_at = _now()
    db.add(row)
    db.commit()
    db.refresh(row)
    sync_message = telnyx_sync_action_message(row, ok=True, linked=linked)
    tpl = survey_template_to_dict(row)
    return {
        "ok": True,
        "success": True,
        "message": sync_message,
        "sync_message": sync_message,
        "telnyx_sync_label": telnyx_sync_ui_label(row),
        "template": tpl,
        "template_name": row.name,
        "approval_status": str(row.status or "").upper(),
        "telnyx_request_mode": telnyx_request_mode,
        "telnyx_template_id": row.telnyx_record_id,
        "category": row.category,
        "rejection_reason": row.rejection_reason,
        "linked_existing_remote": linked,
    }


def _link_existing_remote_template(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    language: str,
    remote_items: list[dict[str, Any]] | None = None,
) -> bool:
    """Attach a local/unlinked row to an already-existing Telnyx/Meta template record."""
    remote_item = TelnyxWhatsappTemplateSyncService.find_remote_template(
        db,
        names=_remote_name_candidates_for_row(row),
        language=language,
        sales_template_key=row.sales_template_key,
        remote_items=remote_items,
    )
    if remote_item is None:
        for fallback_lang in resolve_whatsapp_template_languages(db):
            if fallback_lang == language:
                continue
            remote_item = TelnyxWhatsappTemplateSyncService.find_remote_template(
                db,
                names=_remote_name_candidates_for_row(row),
                language=fallback_lang,
                sales_template_key=row.sales_template_key,
                remote_items=remote_items,
            )
            if remote_item is not None:
                break
    if remote_item is None:
        return False

    _apply_remote_telnyx_item(row, remote_item, overwrite_draft=True)
    remote_lang = str(remote_item.get("language") or "").strip()
    if remote_lang:
        row.language = remote_lang
    if not row.sales_template_key:
        from app.services.sales_whatsapp_telnyx_service import template_key_for_telnyx_name

        row.sales_template_key = template_key_for_telnyx_name(str(remote_item.get("name") or row.name))
    row.updated_at = _now()
    db.add(row)
    db.flush()
    logger.info(
        "survey_wa_template_linked_existing_remote",
        extra={
            "template_id": row.id,
            "template_name": row.name,
            "telnyx_record_id": row.telnyx_record_id,
            "status": row.status,
        },
    )
    return True


def _try_link_existing_remote_template(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    language: str,
    remote_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Link a local/unlinked row to an already-existing Telnyx/Meta template."""
    if not _link_existing_remote_template(
        db,
        row,
        language=language,
        remote_items=remote_items,
    ):
        return None
    return _push_success_response(db, row, telnyx_request_mode="link_existing_remote_template", linked=True)


def _apply_remote_telnyx_item(
    row: TelnyxWhatsappTemplate,
    item: dict[str, Any],
    *,
    overwrite_draft: bool = False,
) -> None:
    record_id = str(item.get("id") or "").strip()
    send_id = _send_template_id_from_api_item(item)
    if record_id:
        row.telnyx_record_id = record_id
    if send_id:
        row.template_id = send_id
    remote_lang = str(item.get("language") or "").strip()
    if remote_lang:
        row.language = remote_lang
    row.status = str(item.get("status") or row.status or "PENDING").upper()
    remote_category = normalize_wa_template_category(item.get("category"), required=False)
    if remote_category:
        row.category = remote_category
    components = item.get("components")
    if isinstance(components, list):
        row.components_json = _dumps(components)
        if overwrite_draft:
            row.draft_components_json = _dumps(_normalize_draft_components(components))
        row.remote_content_hash = _sync_content_hash(components)
        row.body_preview = _body_preview(components)
        row.example_values_json = _dumps(_extract_example_values(components))
    row.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
    waba = item.get("whatsapp_business_account")
    if isinstance(waba, dict):
        waba_id = str(waba.get("id") or "").strip()
        if waba_id:
            row.waba_id = waba_id


def _refresh_local_sync_status(row: TelnyxWhatsappTemplate) -> str:
    draft = _loads(row.draft_components_json)
    remote = _loads(row.components_json)
    if _is_local_row(row):
        return SYNC_DRAFT if isinstance(draft, list) and draft else SYNC_LOCAL_CHANGES
    draft_hash = _sync_content_hash(draft if isinstance(draft, list) else None)
    remote_hash = row.remote_content_hash or _sync_content_hash(remote if isinstance(remote, list) else None)
    if draft_hash and remote_hash and draft_hash != remote_hash:
        return SYNC_LOCAL_CHANGES
    live_remote_hash = _sync_content_hash(remote if isinstance(remote, list) else None)
    if live_remote_hash and row.remote_content_hash and live_remote_hash != row.remote_content_hash:
        return SYNC_REMOTE_CHANGED
    if row.last_push_error:
        return SYNC_ERROR
    return SYNC_IN_SYNC


def _persist_normalized_draft(db: Session, row: TelnyxWhatsappTemplate, components: list[Any]) -> list[Any]:
    """Normalize draft components in DB (strip invalid Meta examples) before push/sync."""
    normalized = _normalize_draft_components(components)
    if _dumps(normalized) != str(row.draft_components_json or ""):
        row.draft_components_json = _dumps(normalized)
        row.example_values_json = _dumps(_example_values_for_storage(normalized))
        row.updated_at = _now()
        db.add(row)
        db.flush()
    return normalized


def survey_template_to_dict(
    row: TelnyxWhatsappTemplate,
    *,
    mapping: SurveyTypeTemplate | None = None,
    linked_survey_type_count: int | None = None,
) -> dict[str, Any]:
    base = template_to_dict(row)
    components = _effective_components(row)
    sync_status = _refresh_local_sync_status(row)
    row.local_sync_status = sync_status
    var_ids = _meta_var_ids_in_components(components)
    examples = _loads(row.example_values_json)
    if not isinstance(examples, list):
        examples = []
    if not var_ids:
        examples = []
    else:
        examples = _example_values_for_storage(components, override=examples)
    workflow = template_workflow_state(row)
    payload = {
        **base,
        "display_name": row.display_name or row.name,
        "customer_description": str(row.customer_description or "").strip() or None,
        "parent_template_id": row.parent_template_id,
        "approval_status": str(row.status or "UNKNOWN").upper(),
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
        "linked_survey_type_count": linked_survey_type_count,
        "step_role": str(row.step_role or "").strip().lower() or None,
        "outcome_key": str(row.outcome_key or "").strip().lower() or None,
        "outcome_variables": _loads(row.outcome_variables_json),
        "privacy_mode": resolve_row_privacy_mode(row),
        "industry_id": row.industry_id,
        "pack_id": row.pack_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **workflow,
    }
    if mapping is not None:
        payload.update(
            {
                "mapping_id": mapping.id,
                "usable_as_standard": bool(mapping.usable_as_standard),
                "usable_as_anonymous": bool(mapping.usable_as_anonymous),
                "is_default_standard": bool(mapping.is_default_standard),
                "is_default_anonymous": bool(mapping.is_default_anonymous),
            }
        )
    # Legacy content hint only — usage is driven by survey_type_templates mappings.
    payload["variant_type"] = row.variant_type or VARIANT_STANDARD
    return payload


class SurveyWhatsappTemplateService:
    @staticmethod
    def list_for_survey_type(
        db: Session,
        survey_type_id: str,
        *,
        privacy_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        survey_type = db.get(SurveyType, survey_type_id)
        target_privacy = normalize_privacy_mode(privacy_mode) if privacy_mode else None
        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id):
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if row is None:
                continue
            if survey_type is not None and not template_belongs_to_survey_type(row, survey_type):
                continue
            if survey_type is not None and not template_matches_survey_industry(row, survey_type, mapping=mapping):
                continue
            if target_privacy is not None:
                row_pm = resolve_row_privacy_mode(row)
                map_pm = resolve_mapping_privacy_mode(mapping, template_row=row)
                if row_pm != target_privacy or map_pm != target_privacy:
                    continue
            linked = SurveyTypeTemplateService.linked_survey_type_count(db, row.id)
            payload.append(survey_template_to_dict(row, mapping=mapping, linked_survey_type_count=linked))
        payload.sort(key=lambda item: (not item.get("is_default_standard"), not item.get("is_default_anonymous"), item.get("name") or ""))
        return payload

    @staticmethod
    def list_library(db: Session) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.active_for_survey.is_(True))
                .order_by(TelnyxWhatsappTemplate.display_name.asc(), TelnyxWhatsappTemplate.name.asc())
            ).scalars().all()
        )
        return [
            survey_template_to_dict(
                row,
                linked_survey_type_count=SurveyTypeTemplateService.linked_survey_type_count(db, row.id),
            )
            for row in rows
        ]

    @staticmethod
    def get_template_detail(db: Session, template_id: int) -> dict[str, Any] | None:
        row = SurveyWhatsappTemplateService.get_template(db, template_id)
        if row is None:
            return None
        return {
            "template": survey_template_to_dict(
                row,
                linked_survey_type_count=SurveyTypeTemplateService.linked_survey_type_count(db, row.id),
            ),
            "mappings": SurveyTypeTemplateService.mappings_payload_for_template(db, template_id),
            "survey_types": SurveyTypeTemplateService.all_survey_types_with_mapping_flags(db, template_id),
        }

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
        language: str | None = None,
        category: str = "UTILITY",
    ) -> TelnyxWhatsappTemplate:
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        components = _default_standard_components()
        lang_raw = str(language or default_wa_template_language(db)).strip()
        lang_code, lang_error = normalize_wa_template_language(lang_raw, db=db)
        if lang_error:
            raise SurveyWhatsappTemplateError(lang_error)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=_telnyx_name_for(survey_type.slug, VARIANT_STANDARD),
            display_name=f"{survey_type.name} — Standard",
            language=lang_code or default_wa_template_language(db),
            category=category,
            status="LOCAL_DRAFT",
            variant_type=VARIANT_STANDARD,
            privacy_mode=PRIVACY_MODE_OFF,
            survey_type_id=survey_type.id,
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
        db.flush()
        has_default = any(
            m.is_default_standard
            for m in SurveyTypeTemplateService.list_for_survey_type(db, survey_type.id)
        )
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=row.id,
            usable_as_standard=True,
            is_default_standard=not has_default,
            privacy_mode=PRIVACY_MODE_OFF,
        )
        db.refresh(row)
        return row

    @staticmethod
    def create_question_draft(
        db: Session,
        *,
        survey_type: SurveyType,
        step_role: str = "rating",
        display_name: str | None = None,
        language: str | None = None,
        category: str = "UTILITY",
        privacy_mode: str = PRIVACY_MODE_OFF,
    ) -> TelnyxWhatsappTemplate:
        from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role

        role = normalize_step_role(step_role)
        if role not in MIDDLE_STEP_ROLES:
            raise SurveyWhatsappTemplateError(
                f"step_role must be a survey question role ({', '.join(MIDDLE_STEP_ROLES)}), not {role!r}"
            )
        pm = normalize_privacy_mode(privacy_mode)
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        components = _default_question_components(step_role=role)
        if pm == PRIVACY_MODE_ON:
            components = _apply_anonymous_wording(components)
        lang_raw = str(language or default_wa_template_language(db)).strip()
        lang_code, lang_error = normalize_wa_template_language(lang_raw, db=db)
        if lang_error:
            raise SurveyWhatsappTemplateError(lang_error)
        label = (display_name or f"{survey_type.name} — {role.replace('_', ' ').title()}").strip()
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=_telnyx_name_for(survey_type.slug, f"{role}_{uuid.uuid4().hex[:6]}"),
            display_name=label[:128],
            language=lang_code or default_wa_template_language(db),
            category=category,
            status="LOCAL_DRAFT",
            variant_type=privacy_mode_to_variant(pm),
            privacy_mode=pm,
            survey_type_id=survey_type.id,
            step_role=role,
            body_preview=_body_preview(components),
            draft_components_json=_dumps(components),
            example_values_json=_dumps([]),
            local_sync_status=SYNC_DRAFT,
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        if pm == PRIVACY_MODE_ON:
            SurveyTypeTemplateService.upsert_mapping(
                db,
                survey_type_id=survey_type.id,
                template_id=row.id,
                usable_as_anonymous=True,
                privacy_mode=pm,
            )
        else:
            SurveyTypeTemplateService.upsert_mapping(
                db,
                survey_type_id=survey_type.id,
                template_id=row.id,
                usable_as_standard=True,
                privacy_mode=pm,
            )
        db.refresh(row)
        return row

    @staticmethod
    def _apply_privacy_mode_to_row(row: TelnyxWhatsappTemplate, privacy_mode: str) -> None:
        pm = normalize_privacy_mode(privacy_mode)
        row.privacy_mode = pm
        row.variant_type = privacy_mode_to_variant(pm)

    @staticmethod
    def _sync_template_privacy_mappings(db: Session, row: TelnyxWhatsappTemplate) -> None:
        pm = resolve_row_privacy_mode(row)
        is_anonymous = pm == PRIVACY_MODE_ON
        for mapping in SurveyTypeTemplateService.list_for_template(db, row.id):
            mapping.privacy_mode = pm
            mapping.usable_as_standard = not is_anonymous
            mapping.usable_as_anonymous = is_anonymous
            if is_anonymous:
                mapping.is_default_standard = False
            else:
                mapping.is_default_anonymous = False
            mapping.updated_at = _now()
            db.add(mapping)

    @staticmethod
    def save_draft(db: Session, row: TelnyxWhatsappTemplate, payload: dict[str, Any]) -> TelnyxWhatsappTemplate:
        if "display_name" in payload:
            row.display_name = str(payload.get("display_name") or row.display_name or row.name).strip() or row.name
        if "customer_description" in payload:
            desc = str(payload.get("customer_description") or "").strip()
            row.customer_description = desc or None
        if "privacy_mode" in payload:
            SurveyWhatsappTemplateService._apply_privacy_mode_to_row(row, str(payload.get("privacy_mode") or ""))
        if "language" in payload and str(payload.get("language") or "").strip():
            lang_code, lang_error = normalize_wa_template_language(str(payload.get("language")), db=db)
            if lang_error:
                raise SurveyWhatsappTemplateError(
                    lang_error,
                    payload={"message": lang_error, "template_name": row.name, "requires_language_fix": True},
                )
            row.language = lang_code or default_wa_template_language(db)
        if "category" in payload:
            row.category = normalize_wa_template_category(payload.get("category"), required=False)
        if "active_for_survey" in payload:
            row.active_for_survey = bool(payload["active_for_survey"])
        if "step_role" in payload:
            raw_role = str(payload.get("step_role") or "").strip().lower()
            row.step_role = raw_role[:32] or None
        components = payload.get("components")
        if isinstance(components, list):
            normalized = _normalize_draft_components(components)
            row.draft_components_json = _dumps(normalized)
            row.body_preview = _body_preview(normalized)
            examples = payload.get("example_values")
            example_list = [str(v) for v in examples] if isinstance(examples, list) else None
            row.example_values_json = _dumps(
                _example_values_for_storage(normalized, override=example_list)
            )
        elif "example_values" in payload and isinstance(payload.get("example_values"), list):
            examples = payload.get("example_values")
            row.example_values_json = _dumps(
                _example_values_for_storage(_effective_components(row), override=examples)
            )
        row.local_sync_status = _refresh_local_sync_status(row)
        row.updated_at = _now()
        db.add(row)
        if "privacy_mode" in payload:
            SurveyWhatsappTemplateService._sync_template_privacy_mappings(db, row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def clone_as_anonymous(
        db: Session,
        parent: TelnyxWhatsappTemplate,
        *,
        survey_type_id: str | None = None,
    ) -> TelnyxWhatsappTemplate:
        survey_type: SurveyType | None = None
        if survey_type_id:
            survey_type = db.get(SurveyType, survey_type_id)
        if survey_type is None:
            mappings = SurveyTypeTemplateService.list_for_template(db, parent.id)
            if mappings:
                survey_type = db.get(SurveyType, mappings[0].survey_type_id)
        if survey_type is None:
            raise SurveyWhatsappTemplateError("Choose a survey type before cloning an anonymous variant")
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
            variant_type=VARIANT_ANONYMOUS,
            privacy_mode=PRIVACY_MODE_ON,
            survey_type_id=survey_type.id,
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
        db.flush()
        has_default = any(
            m.is_default_anonymous
            for m in SurveyTypeTemplateService.list_for_survey_type(db, survey_type.id)
        )
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=row.id,
            usable_as_anonymous=True,
            is_default_anonymous=not has_default,
            privacy_mode=PRIVACY_MODE_ON,
        )
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
    def rename_for_meta_sync(db: Session, row: TelnyxWhatsappTemplate, new_name: str) -> TelnyxWhatsappTemplate:
        clean, name_error = validate_wa_template_name(new_name)
        if name_error:
            raise SurveyWhatsappTemplateError(name_error)
        assert clean is not None
        if clean == str(row.name or "").strip().lower():
            raise SurveyWhatsappTemplateError("Choose a different template name before syncing again.")

        record_id = str(row.telnyx_record_id or "").strip()
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
            row.telnyx_record_id = local_id
            row.template_id = local_id
            row.status = "LOCAL_DRAFT"
            row.remote_content_hash = None
            row.components_json = None
            row.rejection_reason = None

        row.name = clean
        row.local_sync_status = SYNC_DRAFT
        row.last_push_error = None
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def push_to_telnyx(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        raw_components = _effective_components(row)
        if not raw_components:
            raise SurveyWhatsappTemplateError("Template has no components to push")

        raw_components = _persist_normalized_draft(db, row, raw_components)

        approval = str(row.status or "").upper()
        if approval == "APPROVED" and not _is_local_row(row):
            remote_sync_hash = row.remote_content_hash or _sync_content_hash(_loads(row.components_json))
            draft_sync_hash = _sync_content_hash(raw_components)
            if remote_sync_hash and draft_sync_hash and remote_sync_hash != draft_sync_hash:
                raise SurveyWhatsappTemplateError(
                    "This template is APPROVED on Meta. Local draft content differs from the approved version — "
                    "either reset the draft from Telnyx (repair_wa_survey_template_drafts.py --reset-from-remote) "
                    "or clone/rename the template if you need new copy, then Push to Telnyx.",
                    payload={
                        "message": (
                            "This template is APPROVED on Meta. Local draft content differs from the approved version."
                        ),
                        "template_name": row.name,
                        "requires_draft_reset_or_clone": True,
                        "approval_status": approval,
                    },
                )
            return SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)

        components = prepare_components_for_telnyx_push(raw_components, row=row)
        body_comp = _body_component_from_prepared(components)
        if body_comp is not None:
            logger.info(
                "survey_wa_template_push_prepared_body",
                extra={
                    "template_id": row.id,
                    "template_name": row.name,
                    "body_example": body_comp.get("example"),
                },
            )

        category = normalize_wa_template_category(row.category, required=True)

        var_error = validate_meta_variable_order(components)
        if var_error:
            raise SurveyWhatsappTemplateError(
                var_error,
                payload={"message": var_error, "template_name": row.name},
            )

        config = SurveyWhatsappTemplateService._telnyx_config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)
        waba_id = resolve_telnyx_whatsapp_waba_id(db, config, template_waba_id=row.waba_id)
        if not waba_id:
            raise SurveyWhatsappTemplateError(
                "WhatsApp Business Account ID is not configured in Telnyx settings. "
                "Open Admin → Integrations → Telnyx → WhatsApp and set WhatsApp Business Account ID "
                "(Meta WABA id from Telnyx Portal → Messaging → WhatsApp), or connect a WABA on your Telnyx account."
            )

        lang_code, lang_error = normalize_wa_template_language(row.language, db=db)
        if lang_error:
            raise SurveyWhatsappTemplateError(
                lang_error,
                payload=enrich_template_push_error_payload(
                    message=lang_error,
                    template_name=row.name,
                    language=str(row.language or ""),
                    provider_error=None,
                    status_code=422,
                    telnyx_request_mode="create_or_update_template",
                ),
            )
        if lang_code and lang_code != row.language:
            row.language = lang_code
            db.add(row)
            db.flush()

        lang_code = lang_code or default_wa_template_language(db)

        remote_items: list[dict[str, Any]] | None = None
        if _is_local_row(row):
            try:
                remote_items = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db)
            except Exception as exc:
                logger.warning(
                    "survey_wa_template_prefetch_remote_failed",
                    extra={"template_id": row.id, "error": str(exc)},
                )
                remote_items = []
            _link_existing_remote_template(
                db,
                row,
                language=lang_code,
                remote_items=remote_items,
            )

        record_id = str(row.telnyx_record_id or "").strip()
        has_remote_id = bool(record_id) and not record_id.startswith(_LOCAL_ID_PREFIX)

        if has_remote_id:
            patched, patch_error = _patch_remote_template_on_telnyx(
                db,
                row,
                components=components,
                api_key=api_key,
                record_id=record_id,
            )
            if patched is not None:
                return patched
            if patch_error:
                row.last_push_error = patch_error
                row.local_sync_status = SYNC_ERROR
                row.updated_at = _now()
                db.add(row)
                db.commit()
                error_payload = enrich_template_push_error_payload(
                    message=f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                    template_name=row.name,
                    language=row.language,
                    provider_error=patch_error,
                    status_code=502,
                    telnyx_request_mode="patch_template",
                )
                body_comp = _body_component_from_prepared(components)
                if isinstance(body_comp, dict):
                    error_payload["prepared_body_component"] = body_comp
                raise SurveyWhatsappTemplateError(
                    str(error_payload.get("admin_guidance") or error_payload.get("message")),
                    payload=error_payload,
                )

        payload = {
            "name": str(row.name or "").strip(),
            "category": category,
            "language": lang_code,
            "waba_id": waba_id,
            "components": components,
        }
        telnyx_request_mode = "create_or_update_template"
        logger.info(
            "survey_wa_template_push_start",
            extra={
                "template_id": row.id,
                "template_name": row.name,
                "variant": row.variant_type,
                "telnyx_request_mode": telnyx_request_mode,
            },
        )
        try:
            with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
                headers = _telnyx_headers(api_key)
                response = client.post(
                    TELNYX_WHATSAPP_TEMPLATES_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as e:
            detail = _telnyx_http_error_detail(e)
            meta = parse_meta_error_from_provider_detail(detail)
            if meta.get("subcode") == META_SUBCODE_CONTENT_ALREADY_EXISTS or meta.get("kind") == "content_already_exists":
                if _link_existing_remote_template(db, row, language=lang_code):
                    patched, patch_error = _patch_remote_template_on_telnyx(
                        db,
                        row,
                        components=components,
                        api_key=api_key,
                    )
                    if patched is not None:
                        return patched
                    if patch_error:
                        row.last_push_error = patch_error
                        row.local_sync_status = SYNC_ERROR
                        row.updated_at = _now()
                        db.add(row)
                        db.commit()
                        error_payload = enrich_template_push_error_payload(
                            message=f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                            template_name=row.name,
                            language=row.language,
                            provider_error=patch_error,
                            status_code=502,
                            telnyx_request_mode="patch_template",
                        )
                        body_comp = _body_component_from_prepared(components)
                        if isinstance(body_comp, dict):
                            error_payload["prepared_body_component"] = body_comp
                        raise SurveyWhatsappTemplateError(
                            str(error_payload.get("admin_guidance") or error_payload.get("message")),
                            payload=error_payload,
                        ) from e
            row.last_push_error = detail
            row.local_sync_status = SYNC_ERROR
            row.updated_at = _now()
            db.add(row)
            db.commit()
            logger.warning("survey_wa_template_push_failed", extra={"template_id": row.id, "error": detail})
            error_payload = enrich_template_push_error_payload(
                message=f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                template_name=row.name,
                language=row.language,
                provider_error=detail,
                status_code=e.response.status_code if e.response is not None else None,
                telnyx_request_mode=telnyx_request_mode,
            )
            body_comp = next(
                (c for c in components if isinstance(c, dict) and str(c.get("type") or "").upper() == "BODY"),
                None,
            )
            if isinstance(body_comp, dict):
                error_payload["prepared_body_component"] = body_comp
            raise SurveyWhatsappTemplateError(
                str(error_payload.get("admin_guidance") or error_payload.get("message")),
                payload=error_payload,
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

        _apply_remote_telnyx_item(row, item, overwrite_draft=False)
        record_id = str(row.telnyx_record_id or "").strip()
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                remote_item = TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id(db, record_id)
                _apply_remote_telnyx_item(row, remote_item, overwrite_draft=False)
            except Exception as exc:
                logger.warning(
                    "survey_wa_template_refresh_after_push_failed",
                    extra={"template_id": row.id, "telnyx_record_id": record_id, "error": str(exc)},
                )

        return _push_success_response(db, row, telnyx_request_mode=telnyx_request_mode)

    @staticmethod
    def refresh_telnyx_status(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        record_id = str(row.telnyx_record_id or "").strip()
        if not record_id or record_id.startswith(_LOCAL_ID_PREFIX):
            raise SurveyWhatsappTemplateError(
                "Template has not been synced to Telnyx yet. Use Sync to Telnyx first.",
                payload={"message": "Template has not been synced to Telnyx yet. Use Sync to Telnyx first."},
            )
        try:
            remote_item = TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id(db, record_id)
        except Exception as exc:
            detail = str(exc)
            row.last_push_error = detail
            row.local_sync_status = SYNC_ERROR
            row.updated_at = _now()
            db.add(row)
            db.commit()
            raise SurveyWhatsappTemplateError(
                TELNYX_SYNC_FAILED,
                payload=_provider_error_payload(
                    message=TELNYX_SYNC_FAILED,
                    template_name=row.name,
                    provider_error=detail,
                    telnyx_request_mode="fetch_template_status",
                ),
            ) from exc

        _apply_remote_telnyx_item(row, remote_item, overwrite_draft=False)
        row.last_push_error = None
        row.local_sync_status = _refresh_local_sync_status(row)
        row.synced_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        label = telnyx_sync_ui_label(row)
        tpl = survey_template_to_dict(row)
        return {
            "ok": True,
            "success": True,
            "message": label,
            "telnyx_sync_label": label,
            "template": tpl,
            "approval_status": str(row.status or "").upper(),
            "category": row.category,
            "rejection_reason": row.rejection_reason,
            "telnyx_template_id": row.telnyx_record_id,
        }

    @staticmethod
    def push_all_for_survey_type(db: Session, survey_type_id: str) -> dict[str, Any]:
        survey_type = db.get(SurveyType, survey_type_id)
        if survey_type is None:
            raise SurveyWhatsappTemplateError("Survey type not found")

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        pushed = 0
        skipped = 0

        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id):
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if row is None:
                continue
            if not template_belongs_to_survey_type(row, survey_type):
                continue
            if not _effective_components(row):
                skipped += 1
                continue

            label = telnyx_sync_ui_label(row)
            content_sync = _refresh_local_sync_status(row)
            if label == TELNYX_SYNC_APPROVED and content_sync == SYNC_IN_SYNC:
                skipped += 1
                continue
            if label == TELNYX_SYNC_PENDING and content_sync == SYNC_IN_SYNC:
                skipped += 1
                continue

            template_id = row.id
            template_name = row.name
            try:
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                pushed += 1
                results.append(
                    {
                        "template_id": template_id,
                        "template_name": template_name,
                        "ok": True,
                        "message": result.get("sync_message") or result.get("message"),
                        "sync_status": result.get("telnyx_sync_label"),
                    }
                )
            except SurveyWhatsappTemplateError as exc:
                errors.append(
                    {
                        "template_id": template_id,
                        "template_name": template_name,
                        "error": str(exc),
                    }
                )

        return {
            "ok": len(errors) == 0,
            "pushed": pushed,
            "skipped": skipped,
            "error_count": len(errors),
            "errors": errors,
            "results": results,
            "message": f"Pushed {pushed} template(s) to Telnyx"
            + (f", {len(errors)} failed" if errors else "")
            + (f", {skipped} skipped" if skipped else ""),
        }

    @staticmethod
    def push_all_for_industry(db: Session, industry_id: str) -> dict[str, Any]:
        from app.services.industry_service import IndustryService
        from app.services.survey_type_service import SurveyTypeService

        industry = IndustryService.get_industry(db, industry_id)
        if industry is None:
            raise SurveyWhatsappTemplateError("Industry not found")

        survey_types = SurveyTypeService.list_types(db, industry_id=industry_id)
        if not survey_types:
            return {
                "ok": True,
                "pushed": 0,
                "skipped": 0,
                "error_count": 0,
                "errors": [],
                "results": [],
                "survey_type_count": 0,
                "message": "No survey types in this industry",
            }

        total_pushed = 0
        total_skipped = 0
        errors: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []

        for item in survey_types:
            type_id = str(item.get("id") or "").strip()
            type_name = str(item.get("name") or type_id)
            if not type_id:
                continue
            summary = SurveyWhatsappTemplateService.push_all_for_survey_type(db, type_id)
            total_pushed += int(summary.get("pushed") or 0)
            total_skipped += int(summary.get("skipped") or 0)
            for err in summary.get("errors") or []:
                errors.append({**err, "survey_type_id": type_id, "survey_type_name": type_name})
            results.append(
                {
                    "survey_type_id": type_id,
                    "survey_type_name": type_name,
                    "pushed": summary.get("pushed") or 0,
                    "skipped": summary.get("skipped") or 0,
                    "error_count": summary.get("error_count") or 0,
                    "message": summary.get("message"),
                }
            )

        return {
            "ok": len(errors) == 0,
            "pushed": total_pushed,
            "skipped": total_skipped,
            "error_count": len(errors),
            "errors": errors,
            "results": results,
            "survey_type_count": len(survey_types),
            "message": f"Pushed {total_pushed} template(s) across {len(survey_types)} survey type(s)"
            + (f", {len(errors)} failed" if errors else "")
            + (f", {total_skipped} skipped" if total_skipped else ""),
        }

    @staticmethod
    def _ensure_mapping_for_sync(
        db: Session,
        *,
        template: TelnyxWhatsappTemplate,
        name: str,
        survey_type_id: str | None,
    ) -> bool:
        linked = False
        target_types: list[tuple[SurveyType, str]] = []
        lower = name.lower()
        scoped = str(survey_type_id or "").strip()
        all_types = list(db.execute(select(SurveyType)).scalars().all())
        known_slugs = [str(st.slug or "") for st in all_types]

        if scoped:
            st = db.get(SurveyType, scoped)
            if st is not None and template_belongs_to_survey_type(template, st):
                variant = VARIANT_ANONYMOUS if "anonymous" in lower else VARIANT_STANDARD
                target_types.append((st, variant))
        else:
            legacy = re.search(r"voxbulk_survey_([a-z0-9_]+)_(standard|anonymous)$", lower)
            if legacy:
                st = SurveyTypeService.resolve_unique_by_slug(db, legacy.group(1))
                if st is not None:
                    target_types.append((st, legacy.group(2)))

            if not target_types:
                candidates = SurveyTypeService.survey_types_matching_name_slug(db, name, known_slugs=known_slugs)
                if len(candidates) == 1:
                    variant = VARIANT_ANONYMOUS if "anonymous" in lower else VARIANT_STANDARD
                    target_types.append((candidates[0], variant))

        for st, variant in target_types:
            existing = db.execute(
                select(SurveyTypeTemplate).where(
                    SurveyTypeTemplate.survey_type_id == st.id,
                    SurveyTypeTemplate.template_id == template.id,
                )
            ).scalar_one_or_none()
            if existing is None:
                has_std_default = any(
                    m.is_default_standard for m in SurveyTypeTemplateService.list_for_survey_type(db, st.id)
                )
                has_anon_default = any(
                    m.is_default_anonymous for m in SurveyTypeTemplateService.list_for_survey_type(db, st.id)
                )
                try:
                    SurveyTypeTemplateService.upsert_mapping(
                        db,
                        survey_type_id=st.id,
                        template_id=template.id,
                        usable_as_standard=variant == VARIANT_STANDARD,
                        usable_as_anonymous=variant == VARIANT_ANONYMOUS,
                        is_default_standard=variant == VARIANT_STANDARD and not has_std_default,
                        is_default_anonymous=variant == VARIANT_ANONYMOUS and not has_anon_default,
                    )
                except SurveyTypeTemplateError:
                    continue
                linked = True
            else:
                linked = True
            apply_industry_to_template(template, st)
            if variant == VARIANT_ANONYMOUS:
                template.variant_type = VARIANT_ANONYMOUS
            elif not template.variant_type:
                template.variant_type = VARIANT_STANDARD
        return linked

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
                remote_hash = _sync_content_hash(components if isinstance(components, list) else None)
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
                all_slugs = [
                    str(st.slug or "")
                    for st in db.execute(select(SurveyType)).scalars().all()
                ]
                if scoped_type_id:
                    owner = db.get(SurveyType, scoped_type_id)
                else:
                    name_slug = template_name_survey_slug(name, known_slugs=all_slugs)
                    owner = (
                        SurveyTypeService.resolve_unique_by_slug(db, name_slug)
                        if name_slug
                        else None
                    )
                if owner is not None and template_belongs_to_survey_type(existing, owner):
                    existing.survey_type_id = owner.id
                    apply_industry_to_template(existing, owner)
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

                db.flush()

                if SurveyWhatsappTemplateService._ensure_mapping_for_sync(
                    db,
                    template=existing,
                    name=name,
                    survey_type_id=scoped_type_id,
                ):
                    linked += 1

                draft_hash = _sync_content_hash(_loads(existing.draft_components_json))
                if draft_hash and remote_hash and draft_hash != remote_hash:
                    existing.local_sync_status = SYNC_REMOTE_CHANGED
                else:
                    existing.draft_components_json = _dumps(
                        _normalize_draft_components(components if isinstance(components, list) else None)
                    )
                    existing.local_sync_status = SYNC_IN_SYNC
            except Exception as exc:
                failed += 1
                err = f"template parsing error for {item.get('name') or 'unknown'}: {exc}"
                errors.append(err)
                logger.exception("survey_wa_template_sync_item_failed", extra={"template_name": item.get("name")})

        db.commit()

        mapped_ids = select(SurveyTypeTemplate.template_id)
        unlinked = db.execute(
            select(func.count())
            .select_from(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.name.ilike("%survey%"),
                TelnyxWhatsappTemplate.id.not_in(mapped_ids),
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
        template_name = str(row.name or "").strip()
        if not template_name and not send_id:
            raise SurveyWhatsappTemplateError(
                f"Template “{template_label}” has no Telnyx template name or id — push to Telnyx before sending a test."
            )
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
            logger.info(
                "survey_wa_test_send template=%s lang=%s to=%s mode=template_name",
                template_name or send_id,
                lang,
                recipient,
            )
            attempt = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=recipient,
                body=str(preview.get("rendered_body") or row.body_preview or "Survey test"),
                template_name=template_name or None,
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
                logger.info(
                    "survey_wa_test_send template_id=%s lang=%s to=%s mode=template_id",
                    send_id,
                    lang,
                    recipient,
                )
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
    def send_builder_flow_test(
        db: Session,
        *,
        template_ids: list[int],
        to_number: str,
        first_name: str = "Alex",
        business_name: str = "Your business",
        delay_seconds: float = 0.75,
        order_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Deprecated bulk send — use SurveyBuilderTestService.start_wa_test_session instead."""
        if order_id and org_id and user_id:
            from app.services.survey_builder_test_service import SurveyBuilderTestService

            logger.warning(
                "send_builder_flow_test redirected to session flow order_id=%s (template_ids ignored)",
                order_id,
            )
            return SurveyBuilderTestService.start_wa_test_session(
                db,
                org_id=org_id,
                user_id=user_id,
                order_id=order_id,
                test_phone=to_number,
                first_name=first_name,
                business_name=business_name,
            )
        raise SurveyWhatsappTemplateError(
            "Bulk template test send is disabled. Start a survey test session with order_id "
            "so replies follow the wizard workflow step by step."
        )

    @staticmethod
    def update_template_mappings(db: Session, template_id: int, mappings: list[dict[str, Any]]) -> dict[str, Any]:
        row = SurveyWhatsappTemplateService.get_template(db, template_id)
        if row is None:
            raise SurveyWhatsappTemplateError("Template not found")
        saved = SurveyTypeTemplateService.replace_template_mappings(db, template_id, mappings)
        return {
            "ok": True,
            "template_id": template_id,
            "linked_survey_type_count": len(saved),
            "mappings": SurveyTypeTemplateService.mappings_payload_for_template(db, template_id),
            "survey_types": SurveyTypeTemplateService.all_survey_types_with_mapping_flags(db, template_id),
        }

    @staticmethod
    def resolve_for_survey(
        db: Session,
        *,
        survey_type_id: str,
        variant: str,
        language: str | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        return SurveyTypeTemplateService.resolve_default_template(
            db,
            survey_type_id=survey_type_id,
            variant=variant,
            language=language,
        )

    @staticmethod
    def delete_template(
        db: Session,
        row: TelnyxWhatsappTemplate,
    ) -> dict[str, Any]:
        """Delete template from Telnyx (when synced) and remove DB row + mappings."""
        record_id = str(row.telnyx_record_id or "").strip()
        template_id = int(row.id)
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
            except TelnyxWhatsappTemplateSyncError as exc:
                raise SurveyWhatsappTemplateError(
                    f"Telnyx delete failed: {exc}",
                    payload={"message": str(exc), "provider_error": str(exc)},
                ) from exc

        for mapping in SurveyTypeTemplateService.list_for_template(db, template_id):
            db.delete(mapping)
        db.delete(row)
        db.commit()
        return {"ok": True, "message": "Template deleted from Telnyx and database.", "template_id": template_id}

    @staticmethod
    def delete_template_local(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        """Remove template mappings and DB row without calling Telnyx."""
        template_id = int(row.id)
        for mapping in SurveyTypeTemplateService.list_for_template(db, template_id):
            db.delete(mapping)
        db.delete(row)
        db.commit()
        return {
            "ok": True,
            "message": "Template removed from database.",
            "template_id": template_id,
            "local_only": True,
        }

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
