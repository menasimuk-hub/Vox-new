"""Meta/Telnyx WhatsApp template sync — language normalization and provider error handling."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

# Meta WhatsApp template names: lowercase letters, numbers, underscores.
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")

# Meta locale codes: en, en_US, en_GB, pt_BR, etc.
_META_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2}(?:_[A-Z]{2})?$")

_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "en",
    "english": "en_GB",
    "english (uk)": "en_GB",
    "english uk": "en_GB",
    "english (gb)": "en_GB",
    "english gb": "en_GB",
    "british english": "en_GB",
    "en-gb": "en_GB",
    "en_gb": "en_GB",
    "english (us)": "en_US",
    "english us": "en_US",
    "american english": "en_US",
    "en-us": "en_US",
    "en_us": "en_US",
}

# Common Meta template languages (not exhaustive — format is validated separately).
_META_TEMPLATE_LANGUAGES = frozenset(
    {
        "af",
        "sq",
        "ar",
        "az",
        "bn",
        "bg",
        "ca",
        "zh_CN",
        "zh_HK",
        "zh_TW",
        "hr",
        "cs",
        "da",
        "nl",
        "en",
        "en_GB",
        "en_US",
        "et",
        "fil",
        "fi",
        "fr",
        "de",
        "el",
        "gu",
        "he",
        "hi",
        "hu",
        "id",
        "ga",
        "it",
        "ja",
        "kn",
        "kk",
        "ko",
        "lo",
        "lv",
        "lt",
        "mk",
        "ms",
        "mr",
        "nb",
        "fa",
        "pl",
        "pt_BR",
        "pt_PT",
        "pa",
        "ro",
        "ru",
        "sr",
        "sk",
        "sl",
        "es",
        "es_AR",
        "es_ES",
        "es_MX",
        "sw",
        "sv",
        "ta",
        "te",
        "th",
        "tr",
        "uk",
        "ur",
        "vi",
    }
)

META_ERROR_LANGUAGE_DELETION_LOCK = "language_deletion_lock"
META_ERROR_LANGUAGE_UNSUPPORTED = "language_not_supported"
META_ERROR_CONTENT_ALREADY_EXISTS = "content_already_exists"
META_ERROR_MISSING_BODY_EXAMPLE = "missing_body_example"

META_SUBCODE_LANGUAGE_DELETION_LOCK = 2388023
META_SUBCODE_LANGUAGE_UNSUPPORTED = 2388049
META_SUBCODE_CONTENT_ALREADY_EXISTS = 2388024
META_SUBCODE_MISSING_BODY_EXAMPLE = 2388043


def default_wa_template_language(db: Session | None = None) -> str:
    """Platform default locale for new/push templates (UK-first)."""
    try:
        from app.services.sales_whatsapp_telnyx_service import resolve_whatsapp_template_languages

        langs = resolve_whatsapp_template_languages(db)
        if langs:
            return langs[0]
    except Exception:
        pass
    return "en_GB"


def normalize_wa_template_language(raw: str | None, *, db: Session | None = None) -> tuple[str | None, str | None]:
    """
    Normalize stored/admin language to a Meta locale code.
    Returns (code, error_message).
    """
    text = str(raw or "").strip()
    if not text:
        return default_wa_template_language(db), None

    alias_key = text.lower().replace("-", "_").strip()
    alias_key_spaced = text.lower().strip()
    if alias_key_spaced in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[alias_key_spaced], None
    if alias_key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[alias_key], None

    # Already a code like en_GB or en-us
    normalized = text.replace("-", "_")
    if "_" in normalized:
        parts = normalized.split("_", 1)
        candidate = f"{parts[0].lower()}_{parts[1].upper()}"
    else:
        candidate = normalized.lower()

    if not _META_LANGUAGE_CODE_RE.match(candidate):
        return None, (
            f"Invalid template language “{text}”. Use a Meta locale code such as en_GB or en_US "
            "(not display text like “English (US)”)."
        )

    if candidate not in _META_TEMPLATE_LANGUAGES and candidate != "en":
        # Allow well-formed codes even if not in our shortlist — Meta may add locales.
        if not _META_LANGUAGE_CODE_RE.match(candidate):
            return None, f"Template language “{text}” is not a valid Meta locale code."

    return candidate, None


def validate_wa_template_name(name: str | None) -> tuple[str | None, str | None]:
    clean = str(name or "").strip().lower()
    if not clean:
        return None, "Template name is required."
    if not _TEMPLATE_NAME_RE.match(clean):
        return None, (
            "Template name must use lowercase letters, numbers, and underscores only "
            "(Meta/Telnyx requirement)."
        )
    return clean, None


def suggest_alternate_template_name(current_name: str, *, reason: str | None = None) -> str:
    """Suggest a new Telnyx/Meta template name when the current name+language is blocked."""
    base = str(current_name or "").strip().lower() or "template"
    base = re.sub(r"_v\d+$", "", base)
    if reason == META_ERROR_LANGUAGE_DELETION_LOCK:
        for suffix in ("_v2", "_v3", "_v4"):
            candidate = f"{base}{suffix}"
            if _TEMPLATE_NAME_RE.match(candidate):
                return candidate
    return f"{base}_v2" if not base.endswith("_v2") else f"{base}_v3"


def parse_meta_error_from_provider_detail(detail: str | None) -> dict[str, Any]:
    """Extract Meta error fields from Telnyx provider_error text."""
    text = str(detail or "").strip()
    out: dict[str, Any] = {
        "raw": text,
        "subcode": None,
        "code": None,
        "title": None,
        "user_message": None,
        "kind": None,
    }
    if not text:
        return out

    json_blob = text
    marker = "meta api error:"
    if marker in text.lower():
        json_blob = text.split(":", 1)[1].strip()

    parsed: dict[str, Any] | None = None
    if json_blob.startswith("{"):
        try:
            loaded = json.loads(json_blob)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = None

    error_obj = None
    if isinstance(parsed, dict):
        error_obj = parsed.get("error") if isinstance(parsed.get("error"), dict) else parsed

    if isinstance(error_obj, dict):
        out["code"] = error_obj.get("code")
        out["subcode"] = error_obj.get("error_subcode")
        out["title"] = error_obj.get("error_user_title") or error_obj.get("title")
        out["user_message"] = error_obj.get("error_user_msg") or error_obj.get("message")

    if out["subcode"] is None:
        m = re.search(r"error_subcode[\"']?\s*[:=]\s*(\d+)", text)
        if m:
            out["subcode"] = int(m.group(1))

    subcode = out.get("subcode")
    if subcode == META_SUBCODE_LANGUAGE_DELETION_LOCK:
        out["kind"] = META_ERROR_LANGUAGE_DELETION_LOCK
    elif subcode == META_SUBCODE_LANGUAGE_UNSUPPORTED:
        out["kind"] = META_ERROR_LANGUAGE_UNSUPPORTED
    elif subcode == META_SUBCODE_CONTENT_ALREADY_EXISTS:
        out["kind"] = META_ERROR_CONTENT_ALREADY_EXISTS
    elif subcode == META_SUBCODE_MISSING_BODY_EXAMPLE:
        out["kind"] = META_ERROR_MISSING_BODY_EXAMPLE
    elif "missing expected field(s) (example)" in text.lower():
        out["kind"] = META_ERROR_MISSING_BODY_EXAMPLE
    elif "language is being deleted" in text.lower():
        out["kind"] = META_ERROR_LANGUAGE_DELETION_LOCK
    elif "language is not supported" in text.lower():
        out["kind"] = META_ERROR_LANGUAGE_UNSUPPORTED
    elif "content in this language already exists" in text.lower() or "already exists" in text.lower():
        out["kind"] = META_ERROR_CONTENT_ALREADY_EXISTS

    return out


def admin_guidance_for_meta_error(
    *,
    kind: str | None,
    template_name: str | None,
    language: str | None,
    meta_title: str | None = None,
    meta_user_message: str | None = None,
) -> str:
    if kind == META_ERROR_LANGUAGE_DELETION_LOCK:
        suggested = suggest_alternate_template_name(str(template_name or ""), reason=kind)
        lang = language or "this language"
        return (
            f"Meta will not accept new content for template “{template_name}” in {lang} because a previous "
            f"version is still being deleted (typically ~4 weeks). "
            f"Rename the template locally and push again — suggested name: {suggested}. "
            "Do not retry the same name+language until Meta finishes deletion."
        )
    if kind == META_ERROR_LANGUAGE_UNSUPPORTED:
        return (
            f"Meta rejected language “{language}” for template “{template_name}”. "
            "Use a supported locale code (UK accounts usually need en_GB, not en_US or display text). "
            "Save the corrected language, then sync again."
        )
    if kind == META_ERROR_CONTENT_ALREADY_EXISTS:
        return (
            f"Template “{template_name}” already exists on Telnyx/Meta for this language. "
            "The system should link to the existing remote template instead of creating a duplicate — "
            "try Sync again or use Sync from Telnyx to refresh approval status."
        )
    if kind == META_ERROR_MISSING_BODY_EXAMPLE:
        return (
            f"Meta rejected template “{template_name}” because the BODY component was sent without a valid "
            "example. On the VPS, pull the latest API code, restart the service, then run "
            "voxbulk-api/scripts/diagnose_wa_template_push.sh for this template — the prepared BODY must "
            'include "example": {"body_text": [["Sample"]]}. If diagnose looks OK but push still fails, '
            "use Sync to Telnyx (PATCH) instead of creating a duplicate template."
        )
    if meta_user_message:
        return str(meta_user_message)
    if meta_title:
        return str(meta_title)
    return "Telnyx/Meta rejected the template sync request."


def enrich_template_push_error_payload(
    *,
    message: str,
    template_name: str | None,
    language: str | None,
    provider_error: str | None,
    status_code: int | None,
    telnyx_request_mode: str | None = "create_or_update_template",
) -> dict[str, Any]:
    meta = parse_meta_error_from_provider_detail(provider_error)
    kind = meta.get("kind")
    guidance = admin_guidance_for_meta_error(
        kind=kind,
        template_name=template_name,
        language=language,
        meta_title=meta.get("title"),
        meta_user_message=meta.get("user_message"),
    )
    payload: dict[str, Any] = {
        "message": guidance if kind else message,
        "template_name": template_name,
        "language": language,
        "provider_error": provider_error,
        "status_code": status_code,
        "telnyx_request_mode": telnyx_request_mode,
        "meta_error_kind": kind,
        "meta_error_subcode": meta.get("subcode"),
        "meta_error_title": meta.get("title"),
        "meta_error_message": meta.get("user_message"),
        "admin_guidance": guidance,
        "blocking": bool(kind),
        "retry_allowed": not bool(kind),
    }
    if kind == META_ERROR_LANGUAGE_DELETION_LOCK:
        payload["requires_rename"] = True
        payload["suggested_template_name"] = suggest_alternate_template_name(
            str(template_name or ""),
            reason=kind,
        )
    if kind == META_ERROR_LANGUAGE_UNSUPPORTED:
        payload["requires_language_fix"] = True
        payload["suggested_language"] = default_wa_template_language()
    return payload


def http_status_for_template_sync_error(payload: dict[str, Any] | None) -> int:
    """Use 422 for Meta business-rule blocks; reserve 502 for transport/upstream failures."""
    if not payload:
        return 400
    if payload.get("blocking") or payload.get("meta_error_kind"):
        return 422
    if payload.get("provider_error"):
        return 502
    return 400
