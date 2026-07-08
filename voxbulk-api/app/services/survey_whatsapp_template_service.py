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
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
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
from app.services.survey_industry_scope import (
    apply_industry_to_template,
    apply_org_ownership_from_industry,
    template_matches_survey_industry,
    template_visible_to_org,
)
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
    META_SUBCODE_MISSING_BODY_EXAMPLE,
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

SYNC_BRANCH_STATUS_REFRESH = "status_refresh_only"
SYNC_BRANCH_FIRST_PUSH = "first_push"
SYNC_BRANCH_REJECTED_RECOVERY = "rejected_recovery"
SYNC_BRANCH_APPROVED_UPDATE = "approved_update"
SYNC_BRANCH_UNKNOWN = "unknown"


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
    """Build a Meta/Telnyx-compatible BODY component (example only when body uses {{1}} variables)."""
    body = str(text or "").strip()
    var_ids = _meta_var_ids_in_text(body)
    component: dict[str, Any] = {"type": "BODY", "text": body}
    if var_ids:
        examples = [str(v) for v in (example_values or []) if str(v).strip()]
        if not examples:
            examples = _pad_example_values([], max(var_ids))
        body_example = _pad_example_values(examples, max(var_ids))
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


def _normalize_draft_components(
    components: list[Any] | None,
    *,
    step_role: str | None = None,
) -> list[Any]:
    """Persist draft components without Meta-only static examples."""
    if not isinstance(components, list):
        return []
    from app.services.survey_wa_flow_constants import order_scale_button_dicts

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
        elif ctype == "BUTTONS" and step_role:
            buttons = cloned.get("buttons")
            if isinstance(buttons, list) and buttons:
                cloned["buttons"] = order_scale_button_dicts(buttons, step_role=step_role)
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


def _build_meta_buttons_component(comp: dict[str, Any], *, step_role: str | None = None) -> dict[str, Any]:
    from app.services.survey_wa_flow_constants import order_scale_button_dicts

    buttons_in = comp.get("buttons") if isinstance(comp.get("buttons"), list) else []
    if step_role and buttons_in:
        buttons_in = order_scale_button_dicts(buttons_in, step_role=step_role)
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
            step_role = str(getattr(row, "step_role", "") or "") or None
            out.append(_build_meta_buttons_component(comp, step_role=step_role))
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
            text = str(comp.get("text") or "")
            var_ids = _meta_var_ids_in_text(text)
            if var_ids:
                example = comp.get("example")
                if not isinstance(example, dict) or "body_text" not in example:
                    raise SurveyWhatsappTemplateError(
                        "Internal error: BODY example missing after Meta preparation — contact support."
                    )
                if not _meta_example_is_valid(example, field="body_text"):
                    raise SurveyWhatsappTemplateError(
                        "Internal error: BODY example is invalid after Meta preparation — contact support."
                    )
            elif comp.get("example") is not None:
                raise SurveyWhatsappTemplateError(
                    "Internal error: static BODY must not include Meta example values — contact support."
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
            {"type": "QUICK_REPLY", "text": "Excellent"},
            {"type": "QUICK_REPLY", "text": "Good"},
            {"type": "QUICK_REPLY", "text": "Poor"},
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


def _merge_draft_with_remote_components(draft: list[Any], remote: list[Any]) -> list[Any]:
    """Keep local draft body edits but retain Meta-approved BUTTONS/FOOTER when draft omits them."""
    if not draft:
        return remote if isinstance(remote, list) else []
    if not isinstance(remote, list) or not remote:
        return draft
    merged = list(draft)
    draft_types = {str(c.get("type") or "").upper() for c in merged if isinstance(c, dict)}
    for comp in remote:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        if ctype in {"BUTTONS", "FOOTER"} and ctype not in draft_types:
            merged.append(comp)
    return merged


def _preview_render_values(
    *,
    first_name: str,
    business_name: str,
    examples: list[Any],
    placeholder_count: int,
) -> list[str]:
    """Live send/preview values — never show stale Meta example placeholders (e.g. jack / Toyota)."""
    org = str(business_name or "Your business").strip() or "Your business"
    filler = [
        str(first_name or "there").strip() or "there",
        org,
        org,
    ]
    if isinstance(examples, list):
        for i, ex in enumerate(examples):
            while len(filler) <= i:
                filler.append("—")
            if i >= 3 and str(ex or "").strip():
                filler[i] = str(ex).strip()
    while len(filler) < placeholder_count:
        filler.append("—")
    return filler[:placeholder_count] if placeholder_count else filler


def template_row_has_buttons(row: TelnyxWhatsappTemplate | None) -> bool:
    """True when the template has quick-reply/URL/phone buttons (needs Meta approval to send)."""
    if row is None:
        return False
    return bool(_buttons_from_components(_effective_components(row)))


SESSION_TEXT_STEP_ROLES = frozenset(
    {
        "reason",
        "tell_us_more",
        "final_feedback_text",
        "completion",
        "open_question",
    }
)


def _row_system_kind_is_session_text(row: TelnyxWhatsappTemplate) -> bool:
    from app.services.wa_template_utility_content import NO_BUTTON_KINDS

    blob = " ".join(str(v or "") for v in (row.name, row.display_name, row.template_id)).lower()
    return any(kind in blob for kind in NO_BUTTON_KINDS)


def template_row_must_send_as_session_text(row: TelnyxWhatsappTemplate | None) -> bool:
    """Deliver as server session free-form text — never Meta HSM (avoids marketing classification)."""
    if row is None:
        return True
    from app.services.survey_step_bank_service import normalize_step_role

    role = normalize_step_role(row.step_role or "")
    if role in SESSION_TEXT_STEP_ROLES:
        return True
    if _row_system_kind_is_session_text(row):
        return True
    # Welcome/start opens the 24h window via Meta HSM even when the row has no BUTTONS component.
    if role == "start" or "welcome" in str(row.name or "").lower():
        return False
    return not template_row_has_buttons(row)


def template_row_needs_meta_approval(row: TelnyxWhatsappTemplate | None) -> bool:
    """Only buttoned welcome/middle templates require Meta HSM send."""
    if row is None:
        return False
    if template_row_must_send_as_session_text(row):
        return False
    if template_row_has_buttons(row):
        return True
    if not template_row_is_sendable_on_meta(row):
        return False
    from app.services.survey_step_bank_service import normalize_step_role

    role = normalize_step_role(row.step_role or "")
    if role == "start":
        return True
    return "welcome" in str(row.name or "").lower()


def _effective_components(row: TelnyxWhatsappTemplate, *, db: Session | None = None) -> list[Any]:
    draft = _loads(row.draft_components_json)
    remote = _loads(row.components_json)
    draft_list = draft if isinstance(draft, list) and draft else []
    remote_list = remote if isinstance(remote, list) else []
    if db is not None:
        from app.services.wa_system_template_routing_service import WaSystemTemplateRoutingService

        return WaSystemTemplateRoutingService.survey_effective_components(
            db, row, draft_list=draft_list, remote_list=remote_list
        )
    return _merge_draft_with_remote_components(draft_list, remote_list)


def _dashboard_components_for_row(row: TelnyxWhatsappTemplate) -> list[Any]:
    """Dashboard preview/API payload — draft-only for session-text (no legacy Meta BUTTONS)."""
    if template_row_must_send_as_session_text(row):
        draft = _loads(row.draft_components_json)
        if isinstance(draft, list) and draft:
            return draft
        remote = _loads(row.components_json)
        remote_list = remote if isinstance(remote, list) else []
        return [
            c
            for c in remote_list
            if isinstance(c, dict) and str(c.get("type") or "").upper() != "BUTTONS"
        ]
    return _effective_components(row)


def template_row_send_mode(row: TelnyxWhatsappTemplate | None) -> str:
    if template_row_must_send_as_session_text(row):
        return "session_text"
    return "meta_hsm"


def _is_local_row(row: TelnyxWhatsappTemplate) -> bool:
    rid = str(row.telnyx_record_id or "").strip()
    if rid and not rid.startswith(_LOCAL_ID_PREFIX):
        return False
    return rid.startswith(_LOCAL_ID_PREFIX) or str(row.status or "").upper() == "LOCAL_DRAFT"


def _has_remote_telnyx_id(row: TelnyxWhatsappTemplate) -> bool:
    rid = str(row.telnyx_record_id or "").strip()
    return bool(rid) and not rid.startswith(_LOCAL_ID_PREFIX)


def template_row_is_sendable_on_meta(row: TelnyxWhatsappTemplate | None) -> bool:
    """True when Meta/Telnyx can deliver this template (APPROVED + linked remote id)."""
    if row is None:
        return False
    if str(row.status or "").upper() != "APPROVED":
        return False
    return _has_remote_telnyx_id(row)


def resolve_sendable_template_row(
    db: Session,
    row: TelnyxWhatsappTemplate | None,
) -> TelnyxWhatsappTemplate | None:
    """Return APPROVED Meta-linked row — legacy clone when parent hidden or not sendable."""
    if row is None:
        return None

    successors = list(
        db.execute(
            select(TelnyxWhatsappTemplate)
            .where(TelnyxWhatsappTemplate.parent_template_id == int(row.id))
            .order_by(TelnyxWhatsappTemplate.id.desc())
        ).scalars()
    )
    for candidate in successors:
        if candidate.active_for_survey and template_row_is_sendable_on_meta(candidate):
            return candidate

    if bool(row.active_for_survey) and template_row_is_sendable_on_meta(row):
        return row

    if not bool(row.active_for_survey):
        return None

    parent_id = int(row.parent_template_id or 0)
    if parent_id:
        parent = db.get(TelnyxWhatsappTemplate, parent_id)
        if parent and bool(parent.active_for_survey) and template_row_is_sendable_on_meta(parent):
            return parent

    return None


def _content_in_sync(row: TelnyxWhatsappTemplate, raw_components: list[Any]) -> bool:
    remote_hash = row.remote_content_hash or _sync_content_hash(_loads(row.components_json))
    draft_hash = _sync_content_hash(raw_components)
    return bool(remote_hash and draft_hash and remote_hash == draft_hash)


def resolve_template_sync_branch(
    row: TelnyxWhatsappTemplate,
    raw_components: list[Any],
) -> tuple[str, str | None]:
    """Choose sync path: status refresh only vs content submission to Telnyx/Meta."""
    status = str(row.status or "").upper()
    has_remote = _has_remote_telnyx_id(row)
    in_sync = _content_in_sync(row, raw_components)

    if status == "PENDING" and has_remote:
        return SYNC_BRANCH_STATUS_REFRESH, None

    if status == "APPROVED" and has_remote:
        if in_sync:
            return SYNC_BRANCH_STATUS_REFRESH, None
        return SYNC_BRANCH_APPROVED_UPDATE, (
            "This template is APPROVED on Meta. Local draft content differs from the approved version."
        )

    if status == "REJECTED" and has_remote:
        if in_sync:
            return SYNC_BRANCH_STATUS_REFRESH, None
        return SYNC_BRANCH_REJECTED_RECOVERY, None

    if has_remote and in_sync:
        return SYNC_BRANCH_STATUS_REFRESH, None

    if not has_remote:
        return SYNC_BRANCH_FIRST_PUSH, None

    if status in {"", "UNKNOWN"}:
        return SYNC_BRANCH_UNKNOWN, f"Unknown Telnyx/Meta template status “{status or 'empty'}”."

    return SYNC_BRANCH_REJECTED_RECOVERY, None


def _attach_sync_branch(result: dict[str, Any], branch: str) -> dict[str, Any]:
    result["sync_branch"] = branch
    if branch == SYNC_BRANCH_STATUS_REFRESH:
        result["telnyx_request_mode"] = "status_refresh_only"
    return result


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


def _draft_components_for_push(row: TelnyxWhatsappTemplate) -> list[Any]:
    """Local draft is source of truth for push — never prefer remote body text."""
    draft = _loads(row.draft_components_json)
    if isinstance(draft, list) and draft:
        return draft
    return _effective_components(row)


def _find_remote_item_for_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    language: str,
    remote_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    remote_item = TelnyxWhatsappTemplateSyncService.find_remote_template(
        db,
        names=_remote_name_candidates_for_row(row),
        language=language,
        sales_template_key=row.sales_template_key,
        remote_items=remote_items,
    )
    if remote_item is not None:
        return remote_item
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
            return remote_item
    return None


def _apply_remote_link_only(
    db: Session,
    row: TelnyxWhatsappTemplate,
    item: dict[str, Any],
) -> bool:
    """Link Meta record ids and approval fields only — never mirror body/components."""
    record_id = str(item.get("id") or "").strip()
    send_id = _send_template_id_from_api_item(item)
    claimed_record = True
    if record_id:
        owner = db.execute(
            select(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.telnyx_record_id == record_id,
                TelnyxWhatsappTemplate.id != row.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if owner is not None:
            claimed_record = False
            row.status = str(item.get("status") or owner.status or row.status or "PENDING").upper()
        else:
            row.telnyx_record_id = record_id
    if send_id and claimed_record:
        row.template_id = send_id
    elif send_id and not row.template_id:
        row.template_id = send_id
    remote_lang = str(item.get("language") or "").strip()
    if remote_lang and claimed_record:
        row.language = remote_lang
    row.status = str(item.get("status") or row.status or "PENDING").upper()
    remote_category = normalize_wa_template_category(item.get("category"), required=False)
    if remote_category:
        row.category = remote_category
    row.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
    waba = item.get("whatsapp_business_account")
    if isinstance(waba, dict) and claimed_record:
        waba_id = str(waba.get("id") or "").strip()
        if waba_id:
            row.waba_id = waba_id
    row.updated_at = _now()
    db.add(row)
    return claimed_record


def _meta_record_id_for_push(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    language: str,
    remote_items: list[dict[str, Any]] | None = None,
) -> str | None:
    """Resolve Meta template record id for push — link locally when possible."""
    rid = str(row.telnyx_record_id or "").strip()
    if rid and not rid.startswith(_LOCAL_ID_PREFIX):
        return rid
    remote_item = _find_remote_item_for_row(db, row, language=language, remote_items=remote_items)
    if remote_item is None:
        return None
    record_id = str(remote_item.get("id") or "").strip()
    if not record_id:
        return None
    _apply_remote_link_only(db, row, remote_item)
    if _has_remote_telnyx_id(row):
        return str(row.telnyx_record_id or "").strip() or record_id
    return record_id


def fix_survey_template_draft_body_variables(
    components: list[Any] | None,
    *,
    row: TelnyxWhatsappTemplate | None = None,
) -> list[Any]:
    """Normalize stored survey draft components.

    - Static BODY (no {{1}} variables): type + text only — no example values.
    - Variable BODY: keep/rebuild a valid Meta example for each placeholder.
    """
    if not isinstance(components, list):
        return []

    out: list[Any] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        if ctype == "BODY":
            text = str(comp.get("text") or "").strip()
            if not text:
                continue
            var_ids = _meta_var_ids_in_text(text)
            if var_ids:
                examples = _resolve_example_values([comp], row=row)
                out.append(build_meta_body_component(text, example_values=examples))
            else:
                out.append({"type": "BODY", "text": text})
        else:
            out.append(dict(comp))

    return _normalize_draft_components(out)


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
    category: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    rid = str(record_id or row.telnyx_record_id or "").strip()
    if not rid or rid.startswith(_LOCAL_ID_PREFIX):
        return None, None
    patch_payload: dict[str, Any] = {"components": components}
    if category:
        patch_payload["category"] = category
    try:
        with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
            response = client.patch(
                f"{TELNYX_WHATSAPP_TEMPLATES_URL}/{rid}",
                headers=_telnyx_headers(api_key),
                json=patch_payload,
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
    _apply_remote_telnyx_item(db, row, item, overwrite_draft=False)
    return (
        _push_success_response(
            db,
            row,
            telnyx_request_mode="patch_template",
            sync_branch=SYNC_BRANCH_APPROVED_UPDATE,
        ),
        None,
    )


def _raise_patch_push_error(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    components: list[Any],
    patch_error: str,
) -> None:
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



def _push_success_response(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    telnyx_request_mode: str,
    linked: bool = False,
    sync_branch: str | None = None,
    profile_ctx: Any | None = None,
) -> dict[str, Any]:
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

    backup_result = None
    if profile_ctx is not None and not profile_ctx.is_primary:
        backup_result = WaTemplateProfilePushService._snapshot_row(row)

    if profile_ctx is not None:
        WaTemplateProfilePushService.finalize_push(db, row, profile_ctx, mark_pushed=True)

    update_main_row = profile_ctx is None or profile_ctx.is_primary
    if update_main_row:
        row.last_pushed_at = _now()
        row.last_push_error = None
        row.local_sync_status = _refresh_local_sync_status(row)
        row.synced_at = _now()
        row.updated_at = _now()
        db.add(row)
    db.commit()
    if update_main_row:
        db.refresh(row)

    response_row = row
    if backup_result is not None:
        row.telnyx_record_id = backup_result.telnyx_record_id
        row.template_id = backup_result.template_id
        row.status = backup_result.status
        row.category = backup_result.category
        row.rejection_reason = backup_result.rejection_reason
        response_row = row
        if profile_ctx and profile_ctx.snapshot:
            WaTemplateProfilePushService._restore_row(db, row, profile_ctx.snapshot)
            db.add(row)
            db.commit()

    sync_message = telnyx_sync_action_message(response_row, ok=True, linked=linked)
    tpl = survey_template_to_dict(response_row)
    return {
        "ok": True,
        "success": True,
        "message": sync_message,
        "sync_message": sync_message,
        "telnyx_sync_label": telnyx_sync_ui_label(response_row),
        "template": tpl,
        "template_name": response_row.name,
        "approval_status": str(response_row.status or "").upper(),
        "telnyx_request_mode": telnyx_request_mode,
        "telnyx_template_id": response_row.telnyx_record_id,
        "category": response_row.category,
        "rejection_reason": response_row.rejection_reason,
        "linked_existing_remote": linked,
        "sync_branch": sync_branch or telnyx_request_mode,
        "connection_profile_id": getattr(profile_ctx, "connection_profile_id", None) if profile_ctx else None,
    }


def _link_existing_remote_template(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    language: str,
    remote_items: list[dict[str, Any]] | None = None,
) -> bool:
    """Attach a local/unlinked row to an already-existing Telnyx/Meta template record."""
    remote_item = _find_remote_item_for_row(db, row, language=language, remote_items=remote_items)
    if remote_item is None:
        return False

    try:
        with db.begin_nested():
            _apply_remote_link_only(db, row, remote_item)
            if not row.sales_template_key:
                from app.services.sales_whatsapp_telnyx_service import template_key_for_telnyx_name

                row.sales_template_key = template_key_for_telnyx_name(
                    str(remote_item.get("name") or row.name)
                )
            row.updated_at = _now()
            db.add(row)
            db.flush()
    except Exception:
        return False
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


def _prefetch_remote_templates_for_push(
    db: Session,
    *,
    remote_items: list[dict[str, Any]] | None = None,
    template_id: str | None = None,
    connection_profile_id: str | None = None,
    service_code: str | None = "survey",
) -> list[dict[str, Any]]:
    if remote_items is not None:
        return remote_items
    try:
        return TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
    except Exception as exc:
        logger.warning(
            "survey_wa_template_prefetch_remote_failed",
            extra={"template_id": template_id, "error": str(exc)},
        )
        return []


def _resolve_push_language(db: Session, row: TelnyxWhatsappTemplate) -> tuple[str, str | None]:
    lang_code, lang_error = normalize_wa_template_language(row.language, db=db)
    if lang_error:
        return "", lang_error
    resolved = lang_code or default_wa_template_language(db)
    if resolved != row.language:
        row.language = resolved
        db.add(row)
        db.flush()
    return resolved, None


def _try_link_remote_and_resolve_branch(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    raw_components: list[Any],
    language: str,
    remote_items: list[dict[str, Any]] | None,
    connection_profile_id: str | None = None,
    service_code: str | None = "survey",
    skip_remote_link: bool = False,
) -> tuple[str, str | None, bool]:
    linked = False
    if not skip_remote_link and (not _has_remote_telnyx_id(row) or str(row.local_sync_status or "") == SYNC_ERROR):
        linked = _link_existing_remote_template(
            db,
            row,
            language=language,
            remote_items=remote_items if remote_items is not None else [],
        )
        if not linked:
            all_items: list[dict[str, Any]] = []
            if remote_items is not None:
                all_items = remote_items
            elif connection_profile_id:
                try:
                    all_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                        db,
                        connection_profile_id=connection_profile_id,
                        service_code=service_code,
                    )
                except Exception:
                    all_items = []
            else:
                try:
                    all_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
                except Exception:
                    all_items = []
            if all_items:
                linked = _link_existing_remote_template(
                    db,
                    row,
                    language=language,
                    remote_items=all_items,
                )
        if linked:
            db.commit()
            db.refresh(row)
    branch, branch_error = resolve_template_sync_branch(row, raw_components)
    return branch, branch_error, linked


def _push_row_to_meta(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    components: list[Any],
    category: str,
    lang_code: str,
    branch: str,
    prefetched: list[dict[str, Any]] | None,
    connection_profile_id: str | None = None,
    service_code: str | None = "survey",
    profile_ctx: Any | None = None,
) -> dict[str, Any]:
    from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService, MetaWhatsappTemplateError

    template_name = str(row.name or "").strip()
    record_id = str(row.telnyx_record_id or "").strip()
    if record_id.startswith(_LOCAL_ID_PREFIX):
        record_id = ""
    if not record_id:
        record_id = _meta_record_id_for_push(db, row, language=lang_code, remote_items=prefetched) or ""

    meta_request_mode = "create_or_update_template"
    if branch == SYNC_BRANCH_APPROVED_UPDATE and record_id:
        meta_request_mode = "update_approved_same_name"
    elif branch == SYNC_BRANCH_REJECTED_RECOVERY and record_id:
        meta_request_mode = "update_rejected_same_name"
    elif record_id and branch == SYNC_BRANCH_FIRST_PUSH:
        status = str(row.status or "").upper()
        meta_request_mode = (
            "update_rejected_same_name" if status == "REJECTED" else "update_approved_same_name"
        )

    logger.info(
        "survey_wa_template_meta_push_start",
        extra={
            "template_id": row.id,
            "template_name": template_name,
            "meta_request_mode": meta_request_mode,
            "sync_branch": branch,
        },
    )
    try:
        if meta_request_mode in {"update_approved_same_name", "update_rejected_same_name"}:
            item = MetaWhatsappTemplateService.update_message_template(
                db,
                template_id=record_id,
                components=components,
                category=category,
                template_name=template_name,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        else:
            item = MetaWhatsappTemplateService.push_template_payload(
                db,
                name=template_name,
                language=lang_code,
                category=category,
                components=components,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
    except MetaWhatsappTemplateError as exc:
        detail = str(exc)
        meta_payload = exc.payload if isinstance(exc.payload, dict) else {}
        recoverable = meta_payload.get("requires_rename") or meta_payload.get("meta_error_kind") in {
            "content_already_exists",
            "language_deletion_lock",
            "missing_body_example",
        }
        if recoverable:
            recovered = _recover_push_after_provider_conflict(
                db,
                row,
                raw_components=components,
                language=lang_code,
                remote_items=prefetched,
            )
            if recovered is not None:
                return recovered
        row.last_push_error = detail
        row.local_sync_status = SYNC_ERROR
        row.updated_at = _now()
        db.add(row)
        db.commit()
        raise SurveyWhatsappTemplateError(
            detail,
            payload=meta_payload or {"message": detail, "template_name": row.name, "sync_branch": branch},
        ) from exc

    _apply_remote_telnyx_item(db, row, item, overwrite_draft=False, mirror_content=True)
    record_id = str(row.telnyx_record_id or "").strip()
    if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
        try:
            remote_item = MetaWhatsappTemplateService.fetch_by_record_id(db, record_id)
            _apply_remote_telnyx_item(db, row, remote_item, overwrite_draft=False, mirror_content=True)
        except Exception as exc:
            logger.warning(
                "survey_wa_template_meta_refresh_after_push_failed",
                extra={"template_id": row.id, "record_id": record_id, "error": str(exc)},
            )

    return _push_success_response(
        db,
        row,
        telnyx_request_mode=meta_request_mode,
        sync_branch=branch,
        profile_ctx=profile_ctx,
    )


def _push_result_for_sync_branch(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    branch: str,
    branch_error: str | None,
    raw_components: list[Any],
) -> dict[str, Any] | None:
    if branch == SYNC_BRANCH_STATUS_REFRESH:
        pending_before = str(row.status or "").upper() == "PENDING"
        result = SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
        if pending_before:
            db.refresh(row)
            if str(row.status or "").upper() == "PENDING" and not _content_in_sync(row, raw_components):
                raise SurveyWhatsappTemplateError(
                    "Template is PENDING Meta review and local draft differs from the submitted version. "
                    "Wait for Meta approval, or run repair_wa_survey_template_drafts.py --reset-from-remote.",
                    payload={
                        "message": (
                            "Template is PENDING Meta review and local draft differs from the submitted version."
                        ),
                        "template_name": row.name,
                        "requires_draft_reset_or_clone": True,
                        "approval_status": str(row.status or "").upper(),
                        "sync_branch": branch,
                    },
                )
        return _attach_sync_branch(result, branch)
    if branch == SYNC_BRANCH_APPROVED_UPDATE:
        raise SurveyWhatsappTemplateError(
            branch_error
            or "This template is APPROVED on Meta. Local draft content differs from the approved version — "
            "either reset the draft from Meta (repair_wa_survey_template_drafts.py --reset-from-remote) "
            "or clone/rename the template if you need new copy, then Push to Meta.",
            payload={
                "message": branch_error
                or "This template is APPROVED on Meta. Local draft content differs from the approved version.",
                "template_name": row.name,
                "requires_draft_reset_or_clone": True,
                "approval_status": str(row.status or "").upper(),
                "sync_branch": branch,
            },
        )
    return None


def _recover_push_after_provider_conflict(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    raw_components: list[Any],
    language: str,
    remote_items: list[dict[str, Any]] | None,
    force_approved_update: bool = True,
) -> dict[str, Any] | None:
    """When Meta reports duplicate content, link ids and retry push with local draft."""
    items = _prefetch_remote_templates_for_push(
        db,
        remote_items=remote_items,
        template_id=str(row.id or ""),
    )
    linked = _link_existing_remote_template(db, row, language=language, remote_items=items)
    if not linked:
        all_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        linked = _link_existing_remote_template(db, row, language=language, remote_items=all_items)
    if not linked and not _meta_record_id_for_push(db, row, language=language, remote_items=items):
        return None
    db.commit()
    db.refresh(row)
    return SurveyWhatsappTemplateService.push_to_telnyx(
        db,
        row,
        force_approved_update=force_approved_update,
        remote_items=items,
        allow_recovery=False,
    )


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
    db: Session,
    row: TelnyxWhatsappTemplate,
    item: dict[str, Any],
    *,
    overwrite_draft: bool = False,
    mirror_content: bool = True,
) -> bool:
    """Apply remote Meta/Telnyx fields onto a local row.

    Never assigns ``telnyx_record_id`` when another row already owns it
    (unique constraint ``uq_telnyx_wa_tpl_record``). Returns False when the
    remote id was skipped for that reason; status/body may still update.

    When ``mirror_content`` is False, only link ids and status — local draft/body
    are never overwritten (local DB is source of truth for template text).
    """
    record_id = str(item.get("id") or "").strip()
    send_id = _send_template_id_from_api_item(item)
    claimed_record = True
    if record_id:
        owner = db.execute(
            select(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.telnyx_record_id == record_id,
                TelnyxWhatsappTemplate.id != row.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if owner is not None:
            claimed_record = False
            row.status = str(item.get("status") or owner.status or row.status or "PENDING").upper()
        else:
            row.telnyx_record_id = record_id
    if send_id and claimed_record:
        row.template_id = send_id
    elif send_id and not row.template_id:
        row.template_id = send_id
    remote_lang = str(item.get("language") or "").strip()
    if remote_lang and claimed_record:
        row.language = remote_lang
    row.status = str(item.get("status") or row.status or "PENDING").upper()
    remote_category = normalize_wa_template_category(item.get("category"), required=False)
    if remote_category:
        row.category = remote_category
    components = item.get("components")
    if mirror_content and isinstance(components, list):
        # Only overwrite remote components when we own (or claim) the record.
        if claimed_record or not row.components_json:
            row.components_json = _dumps(components)
            if overwrite_draft:
                row.draft_components_json = _dumps(_normalize_draft_components(components))
            row.remote_content_hash = _sync_content_hash(components)
            preview = _body_preview(components)
            if preview:
                row.body_preview = preview
            row.example_values_json = _dumps(_extract_example_values(components))
    row.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
    waba = item.get("whatsapp_business_account")
    if isinstance(waba, dict):
        waba_id = str(waba.get("id") or "").strip()
        if waba_id and claimed_record:
            row.waba_id = waba_id
    return claimed_record


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
    normalized = _normalize_draft_components(components, step_role=str(row.step_role or "") or None)
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
    components = _dashboard_components_for_row(row)
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
    # Dashboard/API preview: draft or merged components first — not stale body_preview column.
    effective_preview = _body_preview(components) or str(row.body_preview or "").strip()
    if effective_preview and not str(row.body_preview or "").strip():
        row.body_preview = effective_preview
    base["body_preview"] = effective_preview
    payload = {
        **base,
        "display_name": row.display_name or row.name,
        "customer_description": str(row.customer_description or "").strip() or None,
        "parent_template_id": row.parent_template_id,
        "approval_status": str(row.status or "UNKNOWN").upper(),
        "sync_status_label": sync_status.replace("_", " ").title(),
        "draft_not_live_on_meta": sync_status in {SYNC_LOCAL_CHANGES, SYNC_DRAFT}
        and str(row.status or "").upper() == "APPROVED",
        "active_for_survey": bool(row.active_for_survey),
        "sync_from_meta": bool(row.sync_from_meta),
        "example_values": examples,
        "draft_components": _loads(row.draft_components_json),
        "remote_components": _loads(row.components_json),
        "buttons": _buttons_from_components(components),
        "send_mode": template_row_send_mode(row),
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
        "org_id": getattr(row, "org_id", None),
        "org_owned": bool(str(getattr(row, "org_id", "") or "").strip()),
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
    def list_for_industry(db: Session, industry_id: str) -> list[dict[str, Any]]:
        """One row per language template (en + ar both listed), including rejected orphans."""
        from app.services.industry_service import _template_ids_for_industry
        from app.services.survey_type_template_service import template_name_survey_slug

        ids = _template_ids_for_industry(db, industry_id)
        if not ids:
            return []
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.id.in_(ids))
                .order_by(TelnyxWhatsappTemplate.name.asc())
            ).scalars()
        )
        type_rows = list(
            db.execute(select(SurveyType).where(SurveyType.industry_id == industry_id)).scalars()
        )
        type_by_id = {st.id: st for st in type_rows}
        known_slugs = [str(st.slug or "") for st in type_rows]
        slug_to_type = {str(st.slug or "").strip().lower(): st for st in type_rows if st.slug}

        # One row per topic + language (drop pack variants abc/utu if still present).
        best: dict[tuple[str, str], TelnyxWhatsappTemplate] = {}
        best_st: dict[tuple[str, str], SurveyType | None] = {}
        for row in rows:
            st = type_by_id.get(str(row.survey_type_id or ""))
            if st is None:
                name_slug = template_name_survey_slug(str(row.name or ""), known_slugs=known_slugs)
                st = slug_to_type.get(str(name_slug or ""))
            type_key = str(st.id if st else row.survey_type_id or row.id)
            lang = str(row.language or "en_GB")
            lang_key = (
                "ar"
                if lang.lower().startswith("ar")
                else "en"
                if lang.lower().startswith("en")
                else lang.lower()
            )
            name = str(row.name or "").lower()
            # System-kind types (e.g. welcome) legitimately keep two variants — a named
            # welcome and an anonymous welcome — under one survey type. Keep them apart so
            # both are counted/listed instead of collapsing into one.
            variant_key = ""
            if st is not None and str(st.system_template_kind or "").strip():
                is_anon = "anonymous" in name or str(row.variant_type or "").strip().lower() == "anonymous"
                variant_key = "anon" if is_anon else "named"
            key = (type_key, lang_key, variant_key)
            score = (
                1 if "_standard" in name and "_abc_" not in name and "_utu_" not in name else 0,
                0 if ("_abc_" in name or "_utu_" in name) else 1,
                row.updated_at.timestamp() if row.updated_at else 0.0,
                -int(row.id or 0),
            )
            cur = best.get(key)
            if cur is None:
                best[key] = row
                best_st[key] = st
                continue
            cur_name = str(cur.name or "").lower()
            cur_score = (
                1 if "_standard" in cur_name and "_abc_" not in cur_name and "_utu_" not in cur_name else 0,
                0 if ("_abc_" in cur_name or "_utu_" in cur_name) else 1,
                cur.updated_at.timestamp() if cur.updated_at else 0.0,
                -int(cur.id or 0),
            )
            if score > cur_score:
                best[key] = row
                best_st[key] = st

        payload: list[dict[str, Any]] = []
        for key, row in best.items():
            st = best_st.get(key)
            linked = SurveyTypeTemplateService.linked_survey_type_count(db, row.id)
            item = survey_template_to_dict(row, linked_survey_type_count=linked)
            item["survey_type_id"] = st.id if st else row.survey_type_id
            item["survey_type_name"] = st.name if st else None
            topic = (st.name if st else None) or item.get("display_name") or item.get("name")
            item["display_name"] = topic
            item["name"] = topic
            lang = str(row.language or "en_GB")
            item["language_count"] = 1
            item["languages"] = [lang]
            payload.append(item)
        payload.sort(
            key=lambda item: (
                0 if str(item.get("status") or "").upper() == "REJECTED" else 1,
                0 if item.get("active_for_survey") is not False else 2,
                str(item.get("name") or ""),
                str(item.get("language") or ""),
            )
        )
        return payload

    @staticmethod
    def list_for_survey_type(
        db: Session,
        survey_type_id: str,
        *,
        privacy_mode: str | None = None,
        include_inactive: bool = True,
        require_approved: bool = False,
        strict_scope: bool = True,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List templates linked to a survey type.

        ``strict_scope=True`` (default) hides mappings that fail name/industry ownership
        checks — used by dashboard/runtime. Admin catalog uses ``strict_scope=False`` so
        every explicit mapping is editable even when Meta-synced rows lack survey_type_id
        or industry_id.
        """
        payload: list[dict[str, Any]] = []
        survey_type = db.get(SurveyType, survey_type_id)
        target_privacy = normalize_privacy_mode(privacy_mode) if privacy_mode else None
        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id):
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if row is None:
                continue
            if org_id is not None and not template_visible_to_org(row, org_id):
                continue
            if not include_inactive and not bool(row.active_for_survey):
                continue
            if (
                require_approved
                and not template_row_is_sendable_on_meta(row)
                and not template_row_must_send_as_session_text(row)
            ):
                continue
            if strict_scope and survey_type is not None and not template_belongs_to_survey_type(row, survey_type):
                continue
            if strict_scope and survey_type is not None and not template_matches_survey_industry(row, survey_type, mapping=mapping):
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
        from app.services.wa_template_utility_content import is_promo_wording

        # Survey/feedback product templates must stay Utility (Meta auto-reclassifies marketing words).
        sales_key = str(row.sales_template_key or "")
        if not sales_key.startswith("sales_"):
            for key in ("display_name", "customer_description"):
                if key in payload and is_promo_wording(payload.get(key)):
                    raise SurveyWhatsappTemplateError(
                        "Marketing words are not allowed in Utility survey templates "
                        "(e.g. promotion, discount, offer, sale, loyalty)."
                    )
            comps = payload.get("components")
            if isinstance(comps, list):
                for comp in comps:
                    if not isinstance(comp, dict):
                        continue
                    if is_promo_wording(comp.get("text")):
                        raise SurveyWhatsappTemplateError(
                            "Marketing words are not allowed in Utility survey templates "
                            "(e.g. promotion, discount, offer, sale, loyalty)."
                        )
                    for btn in comp.get("buttons") or []:
                        if isinstance(btn, dict) and is_promo_wording(btn.get("text") or btn.get("title")):
                            raise SurveyWhatsappTemplateError(
                                "Marketing words are not allowed on Utility template buttons."
                            )
            if "category" in payload:
                cat = str(payload.get("category") or "").upper()
                if cat == "MARKETING" and (
                    row.survey_type_id or str(row.name or "").startswith("voxbulk_survey_")
                ):
                    payload = {**payload, "category": "UTILITY"}

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
            from app.services.wa_template_admin_visibility_service import (
                apply_admin_survey_visibility,
                may_auto_enable_for_survey,
            )

            requested = bool(payload["active_for_survey"])
            if payload.get("_admin_visibility_override"):
                apply_admin_survey_visibility(row, visible=requested)
            elif requested and not may_auto_enable_for_survey(row):
                pass
            else:
                row.active_for_survey = requested
                if requested and hasattr(row, "admin_hidden_from_survey"):
                    row.admin_hidden_from_survey = False
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
    def _telnyx_config(
        db: Session,
        *,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        if connection_profile_id:
            from app.services.connection.config_resolver import (
                WhatsappSyncRouteError,
                resolve_whatsapp_route_by_profile_id,
            )

            try:
                route = resolve_whatsapp_route_by_profile_id(
                    db, connection_profile_id, service_code=service_code or "survey"
                )
            except WhatsappSyncRouteError as exc:
                raise SurveyWhatsappTemplateError(str(exc)) from exc
            if not route.is_telnyx:
                raise SurveyWhatsappTemplateError(
                    f"Connection profile uses {route.provider}, not Telnyx."
                )
            return route.config
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
    def regenerate_rejected_template(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        """Rewrite body to avoid Meta rejection reasons, rename if needed, and push again."""
        from app.services.survey_wa_utility_rewrite_service import apply_utility_rewrite_to_row

        reason = str(row.rejection_reason or row.last_push_error or "").strip()
        status = str(row.status or "").upper()
        if status != "REJECTED" and "reject" not in reason.lower():
            # Still allow regenerate for stuck/error rows.
            pass

        # Detach from rejected remote id so Meta accepts a fresh submission.
        record_id = str(row.telnyx_record_id or "").strip()
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
            row.telnyx_record_id = local_id
            row.template_id = local_id
            row.status = "LOCAL_DRAFT"
            row.rejection_reason = None
            row.last_push_error = None

        # New unique name suffix so Meta does not block the old rejected name.
        base = re.sub(r"_r\d+$", "", str(row.name or "voxbulk_survey_tpl").strip().lower())
        base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")[:100] or "voxbulk_survey_tpl"
        new_name = f"{base}_r{uuid.uuid4().hex[:4]}"
        clean, name_error = validate_wa_template_name(new_name)
        if name_error:
            raise SurveyWhatsappTemplateError(name_error)
        row.name = clean or new_name
        row.local_sync_status = SYNC_DRAFT
        row.updated_at = _now()
        db.add(row)
        db.flush()

        try:
            apply_utility_rewrite_to_row(db, row, use_llm=False)
        except Exception as exc:
            logger.warning("regenerate_rewrite_failed", extra={"template_id": row.id, "error": str(exc)})
            # Fallback: strip marketing-ish phrases that Meta often rejects.
            components = _effective_components(row)
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                if str(comp.get("type") or "").upper() != "BODY":
                    continue
                text = str(comp.get("text") or "")
                text = re.sub(r"\b(buy|sale|discount|promo|offer|free|win)\b", "", text, flags=re.I)
                text = re.sub(r"\s{2,}", " ", text).strip()
                if text:
                    comp["text"] = text
            if components:
                row.draft_components_json = _dumps(_normalize_draft_components(components))
                row.body_preview = _body_preview(components)
                db.add(row)
                db.flush()

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        result["regenerated"] = True
        result["previous_rejection_reason"] = reason or None
        result["new_name"] = row.name
        return result

    @staticmethod
    def ensure_utility_category_for_sync_push(db: Session, row: TelnyxWhatsappTemplate) -> bool:
        """Force UTILITY for survey bulk sync — skip explicit sales/marketing template keys."""
        if str(row.sales_template_key or "").strip():
            return False
        cat = normalize_wa_template_category(row.category, required=False)
        if cat == "UTILITY":
            return False
        row.category = "UTILITY"
        row.updated_at = _now()
        db.add(row)
        db.flush()
        return True

    @staticmethod
    def push_to_telnyx(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        remote_items: list[dict[str, Any]] | None = None,
        force_approved_update: bool = True,
        allow_clone: bool = False,
        allow_recovery: bool = True,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

        profile_ctx = WaTemplateProfilePushService.begin_push(
            db,
            row,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        try:
            return SurveyWhatsappTemplateService._push_to_telnyx_inner(
                db,
                row,
                remote_items=remote_items,
                force_approved_update=force_approved_update,
                allow_clone=allow_clone,
                allow_recovery=allow_recovery,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                profile_ctx=profile_ctx,
            )
        except Exception:
            WaTemplateProfilePushService.abort_push(db, row, profile_ctx)
            raise

    @staticmethod
    def _push_to_telnyx_inner(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        remote_items: list[dict[str, Any]] | None = None,
        force_approved_update: bool = True,
        allow_clone: bool = False,
        allow_recovery: bool = True,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
        profile_ctx: Any | None = None,
    ) -> dict[str, Any]:
        raw_components = _draft_components_for_push(row)
        if not raw_components:
            raise SurveyWhatsappTemplateError("Template has no components to push")

        raw_components = _persist_normalized_draft(db, row, raw_components)

        lang_code, lang_error = _resolve_push_language(db, row)
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

        prefetched = _prefetch_remote_templates_for_push(
            db,
            remote_items=remote_items,
            template_id=str(row.id or ""),
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        branch, branch_error, linked = _try_link_remote_and_resolve_branch(
            db,
            row,
            raw_components=raw_components,
            language=lang_code,
            remote_items=prefetched,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
            skip_remote_link=bool(profile_ctx and not profile_ctx.is_primary),
        )
        if linked:
            logger.info(
                "survey_wa_template_linked_existing_remote_before_branch",
                extra={
                    "template_id": row.id,
                    "template_name": row.name,
                    "telnyx_record_id": row.telnyx_record_id,
                    "approval_status": str(row.status or "").upper(),
                },
            )
            if branch == SYNC_BRANCH_APPROVED_UPDATE and not force_approved_update:
                branch = SYNC_BRANCH_STATUS_REFRESH
                branch_error = None

        if force_approved_update and branch == SYNC_BRANCH_FIRST_PUSH:
            existing_rid = _meta_record_id_for_push(
                db, row, language=lang_code, remote_items=prefetched
            )
            if existing_rid:
                status = str(row.status or "").upper()
                branch = (
                    SYNC_BRANCH_REJECTED_RECOVERY
                    if status == "REJECTED"
                    else SYNC_BRANCH_APPROVED_UPDATE
                )
                branch_error = None

        logger.info(
            "survey_wa_template_sync_branch",
            extra={
                "template_id": row.id,
                "template_name": row.name,
                "sync_branch": branch,
                "approval_status": str(row.status or "").upper(),
                "has_remote_id": _has_remote_telnyx_id(row),
                "force_approved_update": force_approved_update,
            },
        )

        if branch == SYNC_BRANCH_UNKNOWN:
            raise SurveyWhatsappTemplateError(
                branch_error or "Cannot sync template — unknown Telnyx/Meta status.",
                payload={
                    "message": branch_error or "Cannot sync template — unknown Telnyx/Meta status.",
                    "template_name": row.name,
                    "sync_branch": branch,
                },
            )

        if (
            force_approved_update
            and branch == SYNC_BRANCH_STATUS_REFRESH
            and profile_ctx is not None
            and not profile_ctx.is_primary
        ):
            branch = SYNC_BRANCH_FIRST_PUSH
            branch_error = None

        if (
            force_approved_update
            and branch == SYNC_BRANCH_STATUS_REFRESH
            and str(row.status or "").upper() == "APPROVED"
            and _has_remote_telnyx_id(row)
        ):
            branch = SYNC_BRANCH_APPROVED_UPDATE
            branch_error = None

        # Explicit /templates/{id}/push must submit local edits on approved templates.
        if branch == SYNC_BRANCH_APPROVED_UPDATE and not force_approved_update:
            force_approved_update = True
            branch_error = None

        if branch == SYNC_BRANCH_APPROVED_UPDATE and force_approved_update:
            logger.info(
                "survey_wa_template_force_approved_update",
                extra={
                    "template_id": row.id,
                    "template_name": row.name,
                    "approval_status": str(row.status or "").upper(),
                },
            )
        else:
            refresh_result = _push_result_for_sync_branch(
                db,
                row,
                branch=branch,
                branch_error=branch_error,
                raw_components=raw_components,
            )
            if refresh_result is not None:
                if profile_ctx is not None and not profile_ctx.is_primary:
                    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

                    WaTemplateProfilePushService.abort_push(db, row, profile_ctx)
                    db.commit()
                return refresh_result

        components = prepare_components_for_telnyx_push(raw_components, row=row)
        body_comp = _body_component_from_prepared(components)
        if body_comp is not None:
            logger.info(
                "survey_wa_template_push_prepared_body",
                extra={
                    "template_id": row.id,
                    "template_name": row.name,
                    "body_example": body_comp.get("example"),
                    "sync_branch": branch,
                },
            )

        category = normalize_wa_template_category(row.category, required=True)

        var_error = validate_meta_variable_order(components)
        if var_error:
            raise SurveyWhatsappTemplateError(
                var_error,
                payload={"message": var_error, "template_name": row.name, "sync_branch": branch},
            )

        from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

        if is_meta_whatsapp_primary(
            db,
            service_code=service_code,
            connection_profile_id=connection_profile_id,
        ):
            return _push_row_to_meta(
                db,
                row,
                components=components,
                category=normalize_wa_template_category(row.category, required=True),
                lang_code=lang_code,
                branch=branch,
                prefetched=prefetched,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
                profile_ctx=profile_ctx,
            )

        config = SurveyWhatsappTemplateService._telnyx_config(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)
        waba_hint = str(row.waba_id or "").strip() or None
        if profile_ctx is not None and not profile_ctx.is_primary:
            from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

            ledger = WaTemplateProfilePushService.get_ledger_entry(
                db,
                int(row.id),
                profile_ctx.connection_profile_id,
            )
            ledger_waba = str(ledger.waba_id or "").strip() if ledger else ""
            waba_hint = ledger_waba or None
        waba_id = resolve_telnyx_whatsapp_waba_id(db, config, template_waba_id=waba_hint)
        if not waba_id:
            raise SurveyWhatsappTemplateError(
                "WhatsApp Business Account ID is not configured in Telnyx settings. "
                "Open Admin → Integrations → Telnyx → WhatsApp and set WhatsApp Business Account ID "
                "(Meta WABA id from Telnyx Portal → Messaging → WhatsApp), or connect a WABA on your Telnyx account."
            )

        use_patch_for_approved_update = (
            branch in {SYNC_BRANCH_APPROVED_UPDATE, SYNC_BRANCH_REJECTED_RECOVERY}
            and force_approved_update
            and (
                _has_remote_telnyx_id(row)
                or bool(_meta_record_id_for_push(db, row, language=lang_code, remote_items=prefetched))
            )
        )
        if use_patch_for_approved_update:
            telnyx_request_mode = "patch_template"
            logger.info(
                "survey_wa_template_patch_start",
                extra={
                    "template_id": row.id,
                    "template_name": row.name,
                    "variant": row.variant_type,
                    "telnyx_request_mode": telnyx_request_mode,
                    "sync_branch": branch,
                    "telnyx_record_id": row.telnyx_record_id,
                },
            )
            patch_result, patch_error = _patch_remote_template_on_telnyx(
                db,
                row,
                components=components,
                api_key=api_key,
                category=category,
            )
            if patch_result is not None:
                return patch_result
            _raise_patch_push_error(
                db,
                row,
                components=components,
                patch_error=patch_error or "Telnyx PATCH failed for approved template update",
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
                "sync_branch": branch,
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
            recoverable = {
                META_SUBCODE_CONTENT_ALREADY_EXISTS,
                META_SUBCODE_MISSING_BODY_EXAMPLE,
            }
            if allow_recovery and (
                meta.get("subcode") in recoverable
                or meta.get("kind") in {
                    "content_already_exists",
                    "missing_body_example",
                }
            ):
                recovered = _recover_push_after_provider_conflict(
                    db,
                    row,
                    raw_components=raw_components,
                    language=lang_code,
                    remote_items=prefetched,
                    force_approved_update=force_approved_update,
                )
                if recovered is not None:
                    return recovered
            row.last_push_error = detail
            row.local_sync_status = SYNC_ERROR
            row.updated_at = _now()
            db.add(row)
            db.commit()
            logger.warning(
                "survey_wa_template_push_failed",
                extra={"template_id": row.id, "error": detail, "sync_branch": branch},
            )
            error_payload = enrich_template_push_error_payload(
                message=f"Push to Telnyx failed for “{row.display_name or row.name}”.",
                template_name=row.name,
                language=row.language,
                provider_error=detail,
                status_code=e.response.status_code if e.response is not None else None,
                telnyx_request_mode=telnyx_request_mode,
            )
            error_payload["sync_branch"] = branch
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

        _apply_remote_telnyx_item(db, row, item, overwrite_draft=False)
        record_id = str(row.telnyx_record_id or "").strip()
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                remote_item = TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id(
                    db,
                    record_id,
                    connection_profile_id=connection_profile_id,
                    service_code=service_code or "survey",
                )
                _apply_remote_telnyx_item(db, row, remote_item, overwrite_draft=False)
            except Exception as exc:
                logger.warning(
                    "survey_wa_template_refresh_after_push_failed",
                    extra={"template_id": row.id, "telnyx_record_id": record_id, "error": str(exc)},
                )

        return _push_success_response(
            db,
            row,
            telnyx_request_mode=telnyx_request_mode,
            sync_branch=branch,
            profile_ctx=profile_ctx,
        )

    @staticmethod
    def refresh_telnyx_status(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        record_id = str(row.telnyx_record_id or "").strip()
        if not record_id or record_id.startswith(_LOCAL_ID_PREFIX):
            raise SurveyWhatsappTemplateError(
                "Template has not been synced to Meta yet. Use Push to Meta first.",
                payload={"message": "Template has not been synced to Meta yet. Use Push to Meta first."},
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

        _apply_remote_telnyx_item(db, row, remote_item, overwrite_draft=False)
        row.last_push_error = None
        row.local_sync_status = _refresh_local_sync_status(row)
        row.synced_at = _now()
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        if str(row.status or "").upper() == "APPROVED":
            try:
                from app.services.survey_wa_template_supersede_service import (
                    refresh_successor_status_from_meta,
                )

                refresh_successor_status_from_meta(db, row)
            except Exception as exc:  # noqa: BLE001
                logger.warning("supersede_cleanup_after_status_refresh_failed", extra={"error": str(exc)})
        label = telnyx_sync_ui_label(row)
        tpl = survey_template_to_dict(row)
        return {
            "ok": True,
            "success": True,
            "message": label,
            "sync_message": label,
            "telnyx_sync_label": label,
            "template": tpl,
            "approval_status": str(row.status or "").upper(),
            "category": row.category,
            "rejection_reason": row.rejection_reason,
            "telnyx_template_id": row.telnyx_record_id,
            "telnyx_request_mode": "status_refresh_only",
            "sync_branch": SYNC_BRANCH_STATUS_REFRESH,
        }

    @staticmethod
    def push_all_for_survey_type(
        db: Session,
        survey_type_id: str,
        *,
        remote_items: list[dict[str, Any]] | None = None,
        offset: int = 0,
        limit: int | None = None,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        from app.services.wa_template_push_batch_service import run_batched_push

        survey_type = db.get(SurveyType, survey_type_id)
        if survey_type is None:
            raise SurveyWhatsappTemplateError("Survey type not found")

        prefetched = _prefetch_remote_templates_for_push(
            db,
            remote_items=remote_items,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )

        work: list[TelnyxWhatsappTemplate] = []
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
            approval = str(row.status or "").upper()
            if approval not in {"PENDING", "REJECTED"} and label == TELNYX_SYNC_APPROVED and content_sync == SYNC_IN_SYNC:
                skipped += 1
                continue
            work.append(row)

        def push_one(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
            return SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                remote_items=prefetched,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda row: str(row.name or row.id),
        )
        results = []
        errors = []
        for item in batch.get("results") or []:
            tpl = item.get("template") if isinstance(item.get("template"), dict) else {}
            results.append(
                {
                    "template_id": tpl.get("id"),
                    "template_name": tpl.get("name") or item.get("label"),
                    "ok": True,
                    "message": item.get("sync_message") or item.get("message"),
                    "sync_status": item.get("telnyx_sync_label"),
                }
            )
        for err in batch.get("errors") or []:
            errors.append({"template_name": err.get("label"), "error": err.get("error")})

        return {
            "ok": batch.get("ok", True),
            "pushed": batch.get("pushed", 0),
            "skipped": skipped,
            "error_count": batch.get("error_count", 0),
            "errors": errors,
            "results": results,
            "offset": batch.get("offset", offset),
            "limit": batch.get("limit"),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": batch.get("total", len(work)),
            "message": batch.get("message") or f"Pushed {batch.get('pushed', 0)} template(s) to Meta",
        }

    @staticmethod
    def push_all_for_industry(
        db: Session,
        industry_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        from app.services.industry_service import IndustryService
        from app.services.survey_type_service import SurveyTypeService
        from app.services.wa_template_push_batch_service import run_batched_push

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
                "has_more": False,
                "message": "No survey types in this industry",
            }

        prefetched = _prefetch_remote_templates_for_push(db)
        work: list[TelnyxWhatsappTemplate] = []
        skipped = 0
        for item in survey_types:
            type_id = str(item.get("id") or "").strip()
            if not type_id:
                continue
            survey_type = db.get(SurveyType, type_id)
            if survey_type is None:
                continue
            for mapping in SurveyTypeTemplateService.list_for_survey_type(db, type_id):
                row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if row is None or not template_belongs_to_survey_type(row, survey_type):
                    continue
                if not _effective_components(row):
                    skipped += 1
                    continue
                label = telnyx_sync_ui_label(row)
                content_sync = _refresh_local_sync_status(row)
                approval = str(row.status or "").upper()
                if approval not in {"PENDING", "REJECTED"} and label == TELNYX_SYNC_APPROVED and content_sync == SYNC_IN_SYNC:
                    skipped += 1
                    continue
                work.append(row)

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=lambda row: SurveyWhatsappTemplateService.push_to_telnyx(db, row, remote_items=prefetched),
            item_label=lambda row: str(row.name or row.id),
        )
        errors = [{"template_name": err.get("label"), "error": err.get("error")} for err in batch.get("errors") or []]
        return {
            "ok": batch.get("ok", True),
            "pushed": batch.get("pushed", 0),
            "skipped": skipped,
            "error_count": batch.get("error_count", 0),
            "errors": errors,
            "offset": batch.get("offset", offset),
            "limit": batch.get("limit"),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": batch.get("total", len(work)),
            "survey_type_count": len(survey_types),
            "message": batch.get("message") or f"Pushed {batch.get('pushed', 0)} template(s) to Meta",
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
        variant = VARIANT_ANONYMOUS if "anonymous" in lower else VARIANT_STANDARD

        # 1. Explicit scoped survey type (API / industry editor) — do not fall through
        #    to other types when a scope is provided.
        if scoped:
            st = db.get(SurveyType, scoped)
            if st is not None and template_belongs_to_survey_type(template, st):
                target_types.append((st, variant))
        else:
            # 2. Prefer existing ownership on the template row (set at create time).
            owned_id = str(template.survey_type_id or "").strip()
            if owned_id:
                st = db.get(SurveyType, owned_id)
                if st is not None:
                    target_types.append((st, variant))

            # 3. Shared topic slugs: resolve by industry_id + name slug.
            if not target_types:
                industry_id = str(template.industry_id or "").strip()
                name_slug = template_name_survey_slug(name, known_slugs=known_slugs)
                if industry_id and name_slug:
                    st = SurveyTypeService.get_by_slug(
                        db,
                        name_slug,
                        industry_id=industry_id,
                        default_industry_fallback=False,
                    )
                    if st is not None:
                        target_types.append((st, variant))

            # 4. Unique-slug only (never invent a link when the slug spans industries).
            if not target_types:
                legacy = re.search(r"voxbulk_survey_([a-z0-9_]+)_(standard|anonymous)$", lower)
                if legacy:
                    st = SurveyTypeService.resolve_unique_by_slug(db, legacy.group(1))
                    if st is not None:
                        target_types.append((st, legacy.group(2)))

                if not target_types:
                    candidates = SurveyTypeService.survey_types_matching_name_slug(
                        db, name, known_slugs=known_slugs
                    )
                    owner = SurveyWhatsappTemplateService._pick_owner_survey_type(
                        db, candidates, template=template
                    )
                    if owner is not None:
                        target_types.append((owner, variant))

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
                except IntegrityError:
                    db.rollback()
                    # Mapping already exists — still attach ownership for industry cards.
                    if not str(template.survey_type_id or "").strip():
                        template.survey_type_id = st.id
                    if not str(template.industry_id or "").strip():
                        template.industry_id = st.industry_id
                    db.add(template)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    linked = True
                    continue
                linked = True
            else:
                linked = True
            try:
                apply_industry_to_template(template, st)
                apply_org_ownership_from_industry(db, template, str(st.industry_id or ""))
            except Exception:
                pass
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
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
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
                        existing.status = status
                        existing.updated_at = now
                    skipped += 1
                    continue

                send_id = _send_template_id_from_api_item(item)

                existing = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
                ).scalar_one_or_none()
                if existing is None:
                    skipped += 1
                    continue

                updated += 1
                existing.template_id = send_id
                existing.category = str(item.get("category") or "").strip() or existing.category
                existing.status = status
                existing.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
                existing.synced_at = now
                existing.updated_at = now
                existing.local_sync_status = _refresh_local_sync_status(existing)
                db.flush()

                if SurveyWhatsappTemplateService._ensure_mapping_for_sync(
                    db,
                    template=existing,
                    name=str(existing.name or name),
                    survey_type_id=scoped_type_id,
                ):
                    linked += 1
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
    def repair_body_previews(db: Session) -> dict[str, Any]:
        """Rebuild body_preview from stored components when missing or equal to the template name."""
        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        repaired = 0
        for row in rows:
            components = _effective_components(row)
            preview = _body_preview(components)
            if not preview:
                continue
            current = str(row.body_preview or "").strip()
            name = str(row.name or "").strip()
            display = str(row.display_name or "").strip()
            if current and current not in {name, display} and not current.startswith("voxbulk_"):
                continue
            if current == preview:
                continue
            row.body_preview = preview
            db.add(row)
            repaired += 1
        if repaired:
            db.commit()
        return {"ok": True, "repaired": repaired}

    @staticmethod
    def ensure_sales_offer_marketing_category(db: Session) -> dict[str, Any]:
        """Sales offer templates must be MARKETING (not UTILITY) for the Marketing hub tab."""
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    (TelnyxWhatsappTemplate.sales_template_key == "sales_offer")
                    | (TelnyxWhatsappTemplate.name.ilike("%sales_offer%"))
                )
            ).scalars()
        )
        updated = 0
        for row in rows:
            key = str(row.sales_template_key or "").strip().lower()
            name = str(row.name or "").strip().lower()
            if key != "sales_offer" and "sales_offer" not in name and name != "voxbulk_sales_offer":
                continue
            if str(row.category or "").strip().upper() == "MARKETING":
                continue
            row.category = "MARKETING"
            if not row.sales_template_key:
                row.sales_template_key = "sales_offer"
            db.add(row)
            updated += 1
        if updated:
            db.commit()
        return {"ok": True, "updated": updated}

    @staticmethod
    def repair_survey_type_mappings(db: Session) -> dict[str, Any]:
        """Create mappings for active survey templates that have survey_type_id but no mapping row."""
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.active_for_survey.is_(True),
                    TelnyxWhatsappTemplate.survey_type_id.isnot(None),
                )
            ).scalars()
        )
        repaired = 0
        for row in rows:
            st_id = str(row.survey_type_id or "").strip()
            if not st_id:
                continue
            existing = db.execute(
                select(SurveyTypeTemplate).where(
                    SurveyTypeTemplate.survey_type_id == st_id,
                    SurveyTypeTemplate.template_id == row.id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            if SurveyWhatsappTemplateService._ensure_mapping_for_sync(
                db,
                template=row,
                name=str(row.name or ""),
                survey_type_id=st_id,
            ):
                repaired += 1
        if repaired:
            db.commit()
        return {"ok": True, "repaired": repaired}

    @staticmethod
    def _pick_owner_survey_type(
        db: Session,
        candidates: list[SurveyType],
        *,
        template: TelnyxWhatsappTemplate,
    ) -> SurveyType | None:
        """Pick one survey type when a slug exists in multiple industries."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Prefer a type that already has an approved template for the same slug.
        scored: list[tuple[int, str, SurveyType]] = []
        for st in candidates:
            approved = int(
                db.execute(
                    select(func.count())
                    .select_from(TelnyxWhatsappTemplate)
                    .where(
                        TelnyxWhatsappTemplate.survey_type_id == st.id,
                        func.upper(TelnyxWhatsappTemplate.status) == "APPROVED",
                    )
                ).scalar_one()
                or 0
            )
            scored.append((approved, str(st.name or ""), st))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][2]

    @staticmethod
    def relink_survey_templates(db: Session) -> dict[str, Any]:
        """Re-link stored survey templates to survey types using ownership / industry / unique slug."""
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.name.ilike("%survey%"),
                )
            ).scalars()
        )
        all_types = list(db.execute(select(SurveyType)).scalars().all())
        known_slugs = [str(st.slug or "") for st in all_types]
        linked = 0
        ownership_set = 0
        for row in rows:
            if not str(row.survey_type_id or "").strip():
                name_slug = template_name_survey_slug(str(row.name or ""), known_slugs=known_slugs)
                industry_id = str(row.industry_id or "").strip()
                owner = None
                if industry_id and name_slug:
                    owner = SurveyTypeService.get_by_slug(
                        db,
                        name_slug,
                        industry_id=industry_id,
                        default_industry_fallback=False,
                    )
                elif name_slug:
                    owner = SurveyTypeService.resolve_unique_by_slug(db, name_slug)
                    if owner is None:
                        candidates = SurveyTypeService.survey_types_matching_name_slug(
                            db, str(row.name or ""), known_slugs=known_slugs
                        )
                        owner = SurveyWhatsappTemplateService._pick_owner_survey_type(
                            db, candidates, template=row
                        )
                if owner is not None:
                    row.survey_type_id = owner.id
                    # Orphans may be claimed by one industry for ownership; cards also
                    # resolve orphans by name slug via _template_ids_for_industry.
                    if not str(row.industry_id or "").strip():
                        apply_industry_to_template(row, owner)
                        apply_org_ownership_from_industry(db, row, str(owner.industry_id or ""))
                    else:
                        row.survey_type_id = owner.id
                    db.add(row)
                    ownership_set += 1
            if SurveyWhatsappTemplateService._ensure_mapping_for_sync(
                db,
                template=row,
                name=str(row.name or ""),
                survey_type_id=str(row.survey_type_id or "").strip() or None,
            ):
                linked += 1
        db.commit()

        mapped_ids = select(SurveyTypeTemplate.template_id)
        unlinked_templates = int(
            db.execute(
                select(func.count())
                .select_from(TelnyxWhatsappTemplate)
                .where(
                    TelnyxWhatsappTemplate.name.ilike("%survey%"),
                    TelnyxWhatsappTemplate.id.not_in(mapped_ids),
                )
            ).scalar_one()
            or 0
        )
        unlinked_types = 0
        for st in all_types:
            if not SurveyTypeTemplateService.list_for_survey_type(db, st.id):
                unlinked_types += 1
        return {
            "ok": True,
            "linked_to_survey_type": linked,
            "ownership_set": ownership_set,
            "unlinked_survey_templates": unlinked_templates,
            "unlinked_survey_types": unlinked_types,
        }

    @staticmethod
    def sync_hub_from_meta(db: Session) -> dict[str, Any]:
        """Full WA Templates hub sync: Meta catalog status + product linking/repair."""
        from app.services.appointment_whatsapp_template_service import (
            APPOINTMENT_WA_TEMPLATE_KEYS,
            AppointmentWhatsappTemplateService,
            appointment_spec_by_key,
        )
        from app.services.interview_whatsapp_template_service import (
            INTERVIEW_WA_TEMPLATE_KEYS,
            InterviewWhatsappTemplateService,
            interview_spec_by_key,
        )

        catalog = TelnyxWhatsappTemplateSyncService.sync(db)
        # Catalog already refreshed statuses — link/repair without another Meta list call.
        body_repair = SurveyWhatsappTemplateService.repair_body_previews(db)
        sales_cat = SurveyWhatsappTemplateService.ensure_sales_offer_marketing_category(db)
        repair = SurveyWhatsappTemplateService.repair_survey_type_mappings(db)
        relink = SurveyWhatsappTemplateService.relink_survey_templates(db)

        closeout: dict[str, Any] = {}
        try:
            from app.services.wa_template_closeout_service import WaTemplateCloseoutService

            # Link missing types, Utility-only rewrite (EN+AR), push, delete Meta rejects.
            closeout = WaTemplateCloseoutService.run_full_closeout(db)
            catalog = TelnyxWhatsappTemplateSyncService.sync(db)
            closeout["relink_final"] = SurveyWhatsappTemplateService.relink_survey_templates(db)
        except Exception as exc:
            logger.warning("hub_meta_sync_closeout_failed", extra={"error": str(exc)})
            try:
                db.rollback()
            except Exception:
                pass
            closeout["error"] = str(exc)[:300]

        system_kinds: dict[str, int] = {}
        try:
            from app.services.survey_system_template_service import (
                SYSTEM_TEMPLATE_KINDS,
                SurveySystemTemplateService,
            )

            SurveySystemTemplateService.ensure_system_survey_types(db)
            builder = SurveySystemTemplateService.list_templates_for_builder(db)
            templates_by_kind = builder.get("templates") or {}
            for kind in SYSTEM_TEMPLATE_KINDS:
                rows = templates_by_kind.get(kind) or []
                system_kinds[kind] = len(rows)
                # Ensure at least one draft exists so dashboard can pick thank-you / tell-us-more.
                if not rows and kind in {"welcome", "thank_you", "tell_us_more"}:
                    SurveySystemTemplateService.create_draft(db, kind=kind, payload=None)
                    system_kinds[kind] = 1
        except Exception as exc:
            logger.warning("hub_meta_sync_system_templates_failed", extra={"error": str(exc)})

        interview_linked = 0
        appointment_linked = 0
        try:
            InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
            for key in INTERVIEW_WA_TEMPLATE_KEYS:
                spec = interview_spec_by_key(key)
                if not spec:
                    continue
                row = InterviewWhatsappTemplateService._find_row_for_spec(
                    db, key, str(spec.get("telnyx_name") or "")
                )
                if row is None or not _is_local_row(row):
                    continue
                lang_code, _ = normalize_wa_template_language(row.language, db=db)
                if _try_link_existing_remote_template(
                    db, row, language=lang_code or default_wa_template_language(db)
                ):
                    interview_linked += 1
        except Exception as exc:
            logger.warning("hub_meta_sync_interview_failed", extra={"error": str(exc)})

        try:
            AppointmentWhatsappTemplateService.ensure_catalog_seeded(db)
            for key in APPOINTMENT_WA_TEMPLATE_KEYS:
                spec = appointment_spec_by_key(key)
                if not spec:
                    continue
                row = AppointmentWhatsappTemplateService._find_row_for_spec(
                    db, key, str(spec.get("telnyx_name") or "")
                )
                if row is None or not _is_local_row(row):
                    continue
                lang_code, _ = normalize_wa_template_language(row.language, db=db)
                if _try_link_existing_remote_template(
                    db, row, language=lang_code or default_wa_template_language(db)
                ):
                    appointment_linked += 1
        except Exception as exc:
            logger.warning("hub_meta_sync_appointment_failed", extra={"error": str(exc)})

        if interview_linked or appointment_linked:
            db.commit()

        templates = catalog.get("templates") or []
        approved = sum(1 for t in templates if str(t.get("status") or "").upper() == "APPROVED")
        pending = sum(1 for t in templates if str(t.get("status") or "").upper() == "PENDING")
        rejected = sum(1 for t in templates if str(t.get("status") or "").upper() == "REJECTED")
        # Count local-only from DB (authoritative for hub "Local only" filter).
        local_only = int(
            db.execute(
                select(func.count())
                .select_from(TelnyxWhatsappTemplate)
                .where(
                    or_(
                        func.upper(TelnyxWhatsappTemplate.status).in_(["LOCAL_DRAFT", "DRAFT", ""]),
                        TelnyxWhatsappTemplate.telnyx_record_id.like("local-%"),
                    )
                )
            ).scalar_one()
            or 0
        )
        final_relink = closeout.get("relink_final") or closeout.get("relink") or relink
        linked = int(final_relink.get("linked_to_survey_type") or 0)
        unlinked_types = int(final_relink.get("unlinked_survey_types") or 0)
        synced = int(catalog.get("synced") or len(templates))

        message = (
            f"Synced {synced} · Approved {approved} · Pending {pending} · Rejected {rejected} "
            f"· Local only {local_only} · Linked {linked}"
        )
        # Do not return the full template catalog — hundreds of rows make the browser abort
        # waiting for a multi‑MB JSON body. Hub reloads counts via a separate list call.
        return {
            "ok": bool(catalog.get("ok", True)),
            "provider": "meta_whatsapp",
            "message": message,
            "synced": synced,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "local_only": local_only,
            "linked_to_survey_type": linked,
            "unlinked_survey_types": unlinked_types,
            "unlinked_survey_templates": int(final_relink.get("unlinked_survey_templates") or 0),
            "repaired_mappings": int(repair.get("repaired") or 0),
            "repaired_body_previews": int(body_repair.get("repaired") or 0),
            "sales_offer_marketing_updated": int(sales_cat.get("updated") or 0),
            "system_templates": system_kinds,
            "catalog": {k: v for k, v in catalog.items() if k != "templates"},
            "survey": final_relink,
            "interview": closeout.get("interview_push") or {"ok": True, "linked": interview_linked},
            "appointment": {"ok": True, "linked": appointment_linked},
            "closeout": closeout,
            "templates": [],
        }

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
                service_code="survey",
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
                    service_code="survey",
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
        """Delete template from Meta/Telnyx (when synced) and remove DB row + mappings."""
        record_id = str(row.telnyx_record_id or "").strip()
        template_name = str(row.name or "").strip()
        template_id = int(row.id)
        meta_deleted = False
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                TelnyxWhatsappTemplateSyncService.delete_remote_template(
                    db, record_id, template_name=template_name or None
                )
                meta_deleted = True
            except TelnyxWhatsappTemplateSyncError as exc:
                # Still remove locally if Meta already gone.
                if "404" not in str(exc).lower() and "not found" not in str(exc).lower():
                    raise SurveyWhatsappTemplateError(
                        f"Meta delete failed: {exc}",
                        payload={"message": str(exc), "provider_error": str(exc)},
                    ) from exc
        elif template_name:
            from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService
            from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

            if is_meta_whatsapp_primary(db, service_code="survey"):
                try:
                    MetaWhatsappTemplateService.delete_message_template(db, name=template_name)
                    meta_deleted = True
                except MetaWhatsappTemplateError as exc:
                    detail = str(exc).lower()
                    if "404" not in detail and "not found" not in detail:
                        raise SurveyWhatsappTemplateError(
                            f"Meta delete failed: {exc}",
                            payload={"message": str(exc), "provider_error": str(exc)},
                        ) from exc

        for mapping in SurveyTypeTemplateService.list_for_template(db, template_id):
            db.delete(mapping)
        db.delete(row)
        db.commit()
        return {
            "ok": True,
            "message": "Template deleted from Meta and database." if meta_deleted else "Template deleted from database.",
            "template_id": template_id,
            "meta_deleted": meta_deleted,
        }

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

        raw_body_parts: list[str] = []
        footer = ""
        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = str(comp.get("type") or "").upper()
            if ctype == "HEADER":
                fmt = str(comp.get("format") or "TEXT").upper()
                if fmt == "TEXT":
                    raw_body_parts.insert(0, str(comp.get("text") or ""))
            elif ctype == "BODY":
                raw_body_parts.append(str(comp.get("text") or ""))
            elif ctype == "FOOTER":
                footer = str(comp.get("text") or "")

        raw_combined = "\n\n".join(p for p in raw_body_parts if p).strip() or str(row.body_preview or "")
        placeholders = sorted({int(m.group(1)) for m in _VAR_RE.finditer(raw_combined)})
        render_values = _preview_render_values(
            first_name=first_name,
            business_name=business_name,
            examples=examples if isinstance(examples, list) else [],
            placeholder_count=max(placeholders) if placeholders else 0,
        )

        body_parts: list[str] = []
        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = str(comp.get("type") or "").upper()
            if ctype == "HEADER":
                fmt = str(comp.get("format") or "TEXT").upper()
                if fmt == "TEXT":
                    body_parts.insert(0, _render_body_text(str(comp.get("text") or ""), render_values))
            elif ctype == "BODY":
                body_parts.append(_render_body_text(str(comp.get("text") or ""), render_values))

        rendered_body = "\n\n".join(p for p in body_parts if p).strip() or _render_body_text(
            raw_combined,
            render_values,
        )
        buttons = _buttons_from_components(components)
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
