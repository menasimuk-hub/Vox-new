"""Generate reusable WhatsApp survey template packs via OpenAI Responses API."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_template_pack import SurveyTemplatePack
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_industry_scope import (
    SurveyIndustryScopeError,
    apply_industry_to_template,
    load_industry_for_prompt,
    resolve_survey_type_industry_id,
)
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_step_bank_service import ALL_STEP_ROLES, PACK_STEP_ROLES, normalize_step_role
from app.services.wa_template_privacy import (
    PRIVACY_MODE_OFF,
    PRIVACY_MODE_ON,
    normalize_privacy_mode,
    privacy_mode_to_variant,
    validate_privacy_mode_content,
)
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import (
    ANONYMOUS_BODY_SENTENCE,
    ANONYMOUS_FOOTER,
    META_BODY_HARD_MAX_CHARS,
    META_BODY_SOFT_MAX_CHARS,
    META_BUTTON_LABEL_MAX_CHARS,
    META_FOOTER_MAX_CHARS,
    META_HEADER_MAX_CHARS,
    META_QUICK_REPLY_MAX_BUTTONS,
    STANDARD_OPT_OUT_FOOTER,
    SYNC_DRAFT,
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _apply_anonymous_wording,
    _body_preview,
    _dumps,
    _extract_example_values,
    _now,
    survey_template_to_dict,
)

_FOOTER_URL_RE = re.compile(r"https?://", re.I)
_FOOTER_VAR_RE = re.compile(r"\{\{\d+\}\}")

PACK_SIZE = 12

# Prose that mentions "reference" / "ref" — forbidden unless admin instruction explicitly allows it.
_REFERENCE_COPY_RE = re.compile(
    r"\b("
    r"reference(?:\s*(?:number|code|id))?|"
    r"ref\s*#|"
    r"ref\s*:|"
    r"your\s+ref\b|"
    r"ref\s+\{\{3\}\}|"
    r"ref\s+no\.?"
    r")\b",
    re.IGNORECASE,
)


def admin_allows_reference_copy(*, instruction: str = "", purpose: str = "") -> bool:
    """True when admin text explicitly requests reference-style copy."""
    combined = f"{instruction or ''} {purpose or ''}".lower()
    markers = (
        "reference number",
        "reference code",
        "reference id",
        "include reference",
        "use reference",
        "ref number",
        "ref code",
        "case id",
        "ticket id",
        "tracking code",
        "order id",
    )
    return any(m in combined for m in markers)


def copy_contains_forbidden_reference(*parts: str) -> bool:
    text = " ".join(p for p in parts if p).strip()
    if not text:
        return False
    return bool(_REFERENCE_COPY_RE.search(text))


def canonical_footer_for_privacy_mode(*, privacy_mode: str = PRIVACY_MODE_OFF) -> str:
    if normalize_privacy_mode(privacy_mode) == PRIVACY_MODE_ON:
        return ANONYMOUS_FOOTER
    return STANDARD_OPT_OUT_FOOTER


def _button_label_from_dict(btn: dict[str, Any]) -> str:
    """Read button label from OpenAI output (text, label, title, etc.)."""
    if not isinstance(btn, dict):
        return ""
    for key in ("text", "label", "title", "button_text", "name"):
        val = str(btn.get(key) or "").strip()
        if val:
            return val[:META_BUTTON_LABEL_MAX_CHARS]
    return ""


def _default_buttons_for_step(*, step_role: str, button_type: str) -> list[dict[str, Any]]:
    """Sensible Meta-safe defaults when OpenAI leaves button labels empty."""
    role = normalize_step_role(step_role or "")
    bt = _normalize_button_type(button_type)
    empty = {"url": "", "phone_number": ""}
    if bt == "none":
        return []
    if bt == "quick_reply":
        if role == "start":
            return [{"text": "Start survey", **empty}]
        if role == "yes_no":
            return [{"text": "Yes", **empty}, {"text": "No", **empty}]
        if role == "abc_choice":
            return [{"text": "A", **empty}, {"text": "B", **empty}, {"text": "C", **empty}]
        if role == "feeling_word":
            return [{"text": "Great", **empty}, {"text": "Okay", **empty}, {"text": "Poor", **empty}]
        if role == "helpfulness":
            return [{"text": "Yes", **empty}, {"text": "No", **empty}]
        return [{"text": "Continue", **empty}]
    if bt == "url":
        return [{"text": "Open survey", "url": "https://example.com/survey", "phone_number": ""}]
    if bt == "phone":
        return [{"text": "Call us", "url": "", "phone_number": "+441234567890"}]
    return []


def coerce_meta_template_fields(
    item: dict[str, Any],
    *,
    privacy_mode: str = PRIVACY_MODE_OFF,
) -> dict[str, Any]:
    """Normalize OpenAI output to Meta/Telnyx field limits before validation."""
    out = dict(item)
    pm = normalize_privacy_mode(privacy_mode or out.get("privacy_mode"))
    variant = privacy_mode_to_variant(pm)
    out["variant_type"] = variant
    out["footer"] = canonical_footer_for_privacy_mode(privacy_mode=pm)

    header = str(out.get("header") or "").strip()
    if header and _FOOTER_VAR_RE.search(header):
        out["header"] = ""
    elif header:
        out["header"] = header[:META_HEADER_MAX_CHARS]

    body = str(out.get("body") or "").strip()
    if body:
        out["body"] = body[:META_BODY_HARD_MAX_CHARS].rstrip()

    button_type = _normalize_button_type(out.get("button_type"))
    buttons = out.get("buttons") if isinstance(out.get("buttons"), list) else []
    cleaned_buttons: list[dict[str, Any]] = []
    for btn in buttons:
        if not isinstance(btn, dict):
            continue
        label = _button_label_from_dict(btn)
        if not label and button_type == "none":
            continue
        if not label:
            continue
        cleaned_buttons.append(
            {
                "text": label,
                "url": str(btn.get("url") or "").strip(),
                "phone_number": str(btn.get("phone_number") or "").strip(),
            }
        )
    if button_type != "none" and not cleaned_buttons:
        step_role = normalize_step_role(str(out.get("step_role") or out.get("purpose") or ""))
        cleaned_buttons = _default_buttons_for_step(step_role=step_role, button_type=button_type)
    if button_type == "quick_reply":
        cleaned_buttons = cleaned_buttons[:META_QUICK_REPLY_MAX_BUTTONS]
    elif button_type in {"url", "phone"}:
        cleaned_buttons = cleaned_buttons[:1]
    elif button_type == "none":
        cleaned_buttons = []
    out["buttons"] = cleaned_buttons
    out["button_type"] = button_type
    return out


OUTCOME_COMPLETION_KEYS = ("happy", "neutral", "unhappy")
_LOCAL_ID_PREFIX = "local-"
_NAME_RE = re.compile(r"^[a-z0-9_]{3,64}$")
_URL_RE = re.compile(r"^https://[^\s]+$", re.I)
_NEUTRAL_COMPANY_NAMES = frozenset(
    {"voxbulk", "retover", "your business", "company", "business", "the hiring team"}
)


def resolve_wa_survey_company_name(db: Session, *, org_id: str | None = None) -> str | None:
    """Company display name from org profile (AI identity) for WA template generation."""
    from sqlalchemy import select

    from app.models.organisation import Organisation
    from app.models.organisation_ai_config import OrganisationAIIdentity

    resolved_org_id = str(org_id or "").strip() or SurveyWhatsappTemplateService._messaging_org_id(db)
    if not resolved_org_id:
        return None
    org = db.get(Organisation, resolved_org_id)
    if org is None:
        return None

    identity = db.execute(
        select(OrganisationAIIdentity).where(OrganisationAIIdentity.org_id == resolved_org_id).limit(1)
    ).scalar_one_or_none()

    candidates: list[str] = []
    if identity is not None and str(identity.organisation_name or "").strip():
        candidates.append(str(identity.organisation_name).strip())
    if str(org.name or "").strip():
        candidates.append(str(org.name).strip())

    for name in candidates:
        cleaned = name.strip()
        if not cleaned or cleaned.lower() in _NEUTRAL_COMPANY_NAMES:
            continue
        return cleaned
    return None


def _company_name_prompt_block(*, company_name: str | None = None) -> str:
    if company_name:
        return (
            "COMPANY NAME — who the survey is from (Meta variable {{2}}):\n"
            f"• Use the business name “{company_name}” via placeholder {{2}} on the start template and on EVERY "
            "completion template (happy, neutral, unhappy).\n"
            "• Mention {{2}} naturally and briefly so recipients know who is asking — e.g. "
            "“{{2}} would love your feedback” or “Thanks for sharing your thoughts with {{2}}”.\n"
            "• Do NOT use {{2}} on middle question templates (rating, yes_no, reason, follow_up, etc.) — "
            "keep those generic.\n"
            f"• Set example_values[1] (the sample for {{2}}) to “{company_name}” whenever {{2}} appears.\n\n"
        )
    return (
        "COMPANY NAME — no profile name available:\n"
        "• Do not use {{2}} in any template. Write neutral copy without naming a business.\n"
        "• Start and completion templates should still read naturally without a company name.\n\n"
    )

_PACK_TEMPLATE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "template_name": {"type": "string"},
        "variant_type": {"type": "string", "enum": ["standard", "anonymous"]},
        "title": {"type": "string"},
        "step_role": {"type": "string", "enum": list(PACK_STEP_ROLES)},
        # OpenAI strict json_schema: every property must appear in required; use null when N/A.
        "outcome_key": {
            "anyOf": [
                {"type": "string", "enum": list(OUTCOME_COMPLETION_KEYS)},
                {"type": "null"},
            ],
        },
        "purpose": {"type": "string"},
        "body": {"type": "string"},
        "footer": {"type": "string"},
        "header": {"type": "string"},
        "button_type": {"type": "string", "enum": ["none", "quick_reply", "url", "phone"]},
        "buttons": {
            "type": "array",
            "maxItems": META_QUICK_REPLY_MAX_BUTTONS,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "url": {"type": "string"},
                    "phone_number": {"type": "string"},
                },
                "required": ["text", "url", "phone_number"],
                "additionalProperties": False,
            },
        },
        "example_values": {"type": "array", "items": {"type": "string"}},
        "language": {"type": "string"},
        "category": {"type": "string", "enum": ["MARKETING", "UTILITY", "AUTHENTICATION"]},
    },
    "required": [
        "template_name",
        "variant_type",
        "title",
        "step_role",
        "outcome_key",
        "purpose",
        "body",
        "footer",
        "header",
        "button_type",
        "buttons",
        "example_values",
        "language",
        "category",
    ],
    "additionalProperties": False,
}

WA_TEMPLATE_PACK_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "templates": {
            "type": "array",
            "items": _PACK_TEMPLATE_ITEM_SCHEMA,
            "minItems": PACK_SIZE,
            "maxItems": PACK_SIZE,
        }
    },
    "required": ["templates"],
    "additionalProperties": False,
}


WA_SINGLE_TEMPLATE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "template": _PACK_TEMPLATE_ITEM_SCHEMA,
    },
    "required": ["template"],
    "additionalProperties": False,
}


class SurveyWaTemplatePackError(ValueError):
    pass


def _var_re_from_text(text: str) -> list[int]:
    found = [int(m.group(1)) for m in re.finditer(r"\{\{(\d+)\}\}", str(text or ""))]
    return sorted(set(found))


def _slug_token(raw: str, *, fallback: str = "tpl") -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").lower()).strip("_")
    return (token or fallback)[:48]


def _telnyx_pack_name(survey_slug: str, template_name: str) -> str:
    slug = _slug_token(survey_slug, fallback="survey")
    name = _slug_token(template_name, fallback="template")
    return f"voxbulk_survey_{slug}_{name}"[:128]


def _ensure_unique_telnyx_name(db: Session, base_name: str) -> str:
    candidate = base_name[:128]
    suffix = 2
    while db.execute(
        select(TelnyxWhatsappTemplate.id).where(TelnyxWhatsappTemplate.name == candidate).limit(1)
    ).scalar_one_or_none():
        tail = f"_{suffix}"
        candidate = f"{base_name[: 128 - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _normalize_category(raw: str) -> str:
    cat = str(raw or "MARKETING").strip().upper()
    return cat if cat in {"MARKETING", "UTILITY", "AUTHENTICATION"} else "MARKETING"


def _normalize_button_type(raw: str) -> str:
    key = str(raw or "none").strip().lower()
    return key if key in {"none", "quick_reply", "url", "phone"} else "none"


def _build_buttons_component(button_type: str, buttons: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    bt = _normalize_button_type(button_type)
    if bt == "none":
        return None
    cleaned = [b for b in buttons if isinstance(b, dict) and str(b.get("text") or "").strip()]
    if bt == "quick_reply":
        out = []
        for btn in cleaned[:META_QUICK_REPLY_MAX_BUTTONS]:
            label = str(btn.get("text") or "").strip()[:25]
            if label:
                out.append({"type": "QUICK_REPLY", "text": label})
        return out or None
    if bt == "url":
        btn = cleaned[0] if cleaned else {}
        label = str(btn.get("text") or "Open link").strip()[:25]
        url = str(btn.get("url") or "").strip()
        if not label or not _URL_RE.match(url):
            return None
        return [{"type": "URL", "text": label, "url": url}]
    if bt == "phone":
        btn = cleaned[0] if cleaned else {}
        label = str(btn.get("text") or "Call us").strip()[:25]
        phone = str(btn.get("phone_number") or "").strip()
        if not label or not phone:
            return None
        return [{"type": "PHONE_NUMBER", "text": label, "phone_number": phone}]
    return None


def build_components_from_generated(item: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    header = str(item.get("header") or "").strip()
    body = str(item.get("body") or "").strip()
    footer = str(item.get("footer") or "").strip()
    examples = [str(v) for v in (item.get("example_values") or []) if str(v).strip()]
    if not examples:
        examples = ["Alex", "Northgate Dental", "https://example.com/s/abc", "Monday 9am"]

    if header:
        components.append({"type": "HEADER", "format": "TEXT", "text": header[:60]})

    body_example = examples[: max(1, len(_var_re_from_text(body + " " + header)))]
    if not body_example:
        body_example = [examples[0]]
    components.append(
        {
            "type": "BODY",
            "text": body,
            "example": {"body_text": [body_example]},
        }
    )
    if footer:
        components.append({"type": "FOOTER", "text": footer[:60]})

    button_type = _normalize_button_type(item.get("button_type"))
    btn_list = item.get("buttons") if isinstance(item.get("buttons"), list) else []
    built_buttons = _build_buttons_component(button_type, btn_list)
    if built_buttons:
        components.append({"type": "BUTTONS", "buttons": built_buttons})

    variant = str(item.get("variant_type") or VARIANT_STANDARD).strip().lower()
    if variant == VARIANT_ANONYMOUS:
        components = _apply_anonymous_wording(components)

    return components


def validate_generated_template(
    item: dict[str, Any],
    *,
    survey_type: SurveyType | None = None,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    company_name: str | None = None,
    apply_company_name_rules: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return None, ["Template must be an object"]

    privacy_mode = normalize_privacy_mode(privacy_mode)
    if not item.get("privacy_mode") and str(item.get("variant_type") or "").strip().lower() == VARIANT_ANONYMOUS:
        privacy_mode = PRIVACY_MODE_ON
    forced_variant = privacy_mode_to_variant(privacy_mode)

    template_name = _slug_token(item.get("template_name"), fallback="")
    if not template_name or not _NAME_RE.match(template_name):
        errors.append("template_name must be 3–64 lowercase letters, numbers, or underscores")

    variant = str(item.get("variant_type") or forced_variant).strip().lower()
    if variant not in {VARIANT_STANDARD, VARIANT_ANONYMOUS}:
        errors.append("variant_type must be standard or anonymous")
    if variant != forced_variant:
        errors.append(
            f"variant_type must be {forced_variant} for Privacy Mode "
            f"{'On' if privacy_mode == PRIVACY_MODE_ON else 'Off'}"
        )

    body = str(item.get("body") or "").strip()
    if not body:
        errors.append("body is required")
    if len(body) > META_BODY_HARD_MAX_CHARS:
        errors.append(f"body exceeds WhatsApp length guidance ({META_BODY_HARD_MAX_CHARS} chars)")
    elif len(body) > META_BODY_SOFT_MAX_CHARS:
        pass  # soft limit — prompt targets ≤550; hard reject only above 1024

    footer = str(item.get("footer") or "").strip()
    required_footer = canonical_footer_for_privacy_mode(privacy_mode=privacy_mode)
    if not footer:
        errors.append("footer is required")
    elif len(footer) > META_FOOTER_MAX_CHARS:
        errors.append(f"footer exceeds {META_FOOTER_MAX_CHARS} characters (Meta limit)")
    elif _FOOTER_VAR_RE.search(footer):
        errors.append("footer must not contain {{variables}} — Meta only allows plain text in footers")
    elif _FOOTER_URL_RE.search(footer):
        errors.append("footer must not contain URLs — put privacy links in the body only")
    elif footer != required_footer:
        errors.append(
            f'footer must be exactly “{required_footer}” ({len(required_footer)} chars) for Meta approval'
        )

    header = str(item.get("header") or "").strip()
    if header and len(header) > META_HEADER_MAX_CHARS:
        errors.append(f"header exceeds {META_HEADER_MAX_CHARS} characters")
    if header and _FOOTER_VAR_RE.search(header):
        errors.append("header must not contain {{variables}}")

    combined = f"{header} {body}"
    var_ids = _var_re_from_text(combined)
    if var_ids:
        expected = list(range(1, max(var_ids) + 1))
        if var_ids != expected:
            errors.append(f"variables must be sequential from {{{{1}}}} — found {var_ids}")

    examples = [str(v) for v in (item.get("example_values") or []) if str(v).strip()]
    if not examples:
        errors.append("example_values must include at least one sample value")
    elif var_ids and len(examples) < max(var_ids):
        errors.append(f"example_values must include at least {max(var_ids)} value(s) for used variables")

    button_type = _normalize_button_type(item.get("button_type"))
    buttons = item.get("buttons") if isinstance(item.get("buttons"), list) else []
    if button_type == "none" and buttons:
        errors.append("button_type none must have an empty buttons array")
    if button_type == "quick_reply":
        labels = [str(b.get("text") or "").strip() for b in buttons if isinstance(b, dict)]
        labels = [label for label in labels if label]
        if not labels:
            errors.append("quick_reply templates need at least one button label")
        elif len(labels) > META_QUICK_REPLY_MAX_BUTTONS:
            errors.append(
                f"quick_reply supports at most {META_QUICK_REPLY_MAX_BUTTONS} buttons (Meta/VoxBulk limit — never generate 4+)"
            )
        for label in labels:
            if len(label) > META_BUTTON_LABEL_MAX_CHARS:
                errors.append(
                    f"button label “{label[:20]}…” exceeds {META_BUTTON_LABEL_MAX_CHARS} characters (Meta limit)"
                )
    elif button_type == "url":
        if len([b for b in buttons if isinstance(b, dict) and str(b.get("text") or "").strip()]) > 1:
            errors.append("url button templates allow exactly one button")
        btn = buttons[0] if buttons else {}
        url = str(btn.get("url") or "").strip() if isinstance(btn, dict) else ""
        label = str(btn.get("text") or "").strip() if isinstance(btn, dict) else ""
        if not label:
            errors.append("url button templates need button text")
        elif len(label) > META_BUTTON_LABEL_MAX_CHARS:
            errors.append(f"url button label exceeds {META_BUTTON_LABEL_MAX_CHARS} characters")
        if not _URL_RE.match(url):
            errors.append("url button templates need a valid https URL")
    elif button_type == "phone":
        if len([b for b in buttons if isinstance(b, dict) and str(b.get("text") or "").strip()]) > 1:
            errors.append("phone button templates allow exactly one button")
        btn = buttons[0] if buttons else {}
        phone = str(btn.get("phone_number") or "").strip() if isinstance(btn, dict) else ""
        label = str(btn.get("text") or "").strip() if isinstance(btn, dict) else ""
        if not phone:
            errors.append("phone button templates need phone_number")
        if label and len(label) > META_BUTTON_LABEL_MAX_CHARS:
            errors.append(f"phone button label exceeds {META_BUTTON_LABEL_MAX_CHARS} characters")

    if variant == VARIANT_ANONYMOUS:
        if ANONYMOUS_BODY_SENTENCE.lower() not in body.lower():
            errors.append("anonymous templates must mention the survey is anonymous in the body")
        if footer != ANONYMOUS_FOOTER:
            errors.append(f"anonymous templates must use footer “{ANONYMOUS_FOOTER}”")
    elif footer != STANDARD_OPT_OUT_FOOTER:
        errors.append(f'standard templates must use footer “{STANDARD_OPT_OUT_FOOTER}”')

    errors.extend(
        validate_privacy_mode_content(
            privacy_mode=privacy_mode,
            header=header,
            body=body,
            footer=footer,
            example_values=examples,
        )
    )

    if survey_type is not None:
        telnyx_name = _telnyx_pack_name(survey_type.slug, template_name or "template")
        if len(telnyx_name) < 8:
            errors.append("resolved Telnyx template name is too short")

    step_role = normalize_step_role(item.get("step_role") or item.get("purpose") or "")
    if step_role not in ALL_STEP_ROLES:
        errors.append(f"step_role must be one of: {', '.join(PACK_STEP_ROLES)}")
    outcome_key = str(item.get("outcome_key") or "").strip().lower() or None
    if step_role == "completion":
        if outcome_key not in OUTCOME_COMPLETION_KEYS:
            errors.append("completion templates must include outcome_key: happy, neutral, or unhappy")
    elif outcome_key:
        errors.append("outcome_key is only allowed on completion templates")

    if not admin_allows_reference_copy(instruction=instruction, purpose=purpose):
        button_text = " ".join(
            str(b.get("text") or "")
            for b in buttons
            if isinstance(b, dict)
        )
        if copy_contains_forbidden_reference(header, body, footer, button_text):
            errors.append(
                'Do not use "reference", "ref", or reference-style wording unless Admin instruction explicitly asks for it'
            )

    company = str(company_name or "").strip() or None
    has_var2 = "{{2}}" in combined
    if apply_company_name_rules:
        if company:
            if step_role == "start" and not has_var2:
                errors.append(
                    "start template must include {{2}} (company name) when a company profile name is available"
                )
            if step_role == "completion" and not has_var2:
                errors.append(
                    "completion template must include {{2}} (company name) when a company profile name is available"
                )
        elif has_var2:
            errors.append(
                "Do not use {{2}} when no company profile name is available — use neutral wording instead"
            )

    if errors:
        return None, errors

    normalized = {
        "template_name": template_name,
        "variant_type": forced_variant,
        "privacy_mode": privacy_mode,
        "title": str(item.get("title") or template_name).strip()[:128],
        "step_role": step_role,
        "purpose": str(item.get("purpose") or step_role).strip()[:128],
        "body": body,
        "footer": footer,
        "header": header,
        "button_type": button_type,
        "buttons": buttons,
        "example_values": examples,
        "language": str(item.get("language") or "en_US").strip() or "en_US",
        "category": _normalize_category(item.get("category")),
        "service_type": survey_type.slug if survey_type else str(item.get("service_type") or ""),
        "components": build_components_from_generated(item),
        "outcome_key": outcome_key,
        "outcome_variables": item.get("outcome_variables"),
    }
    if company and has_var2:
        examples_out = list(normalized["example_values"])
        while len(examples_out) < 2:
            examples_out.append("")
        examples_out[1] = company
        normalized["example_values"] = examples_out
    return normalized, []


def _validate_pack_composition(items: list[dict[str, Any]]) -> list[str]:
    """Ensure 12-pack has one start, eight middle roles, three completion outcomes."""
    from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES

    errors: list[str] = []
    if len(items) != PACK_SIZE:
        errors.append(f"Expected {PACK_SIZE} templates, got {len(items)}")
    roles_seen: set[str] = set()
    outcomes_seen: set[str] = set()
    for item in items:
        role = normalize_step_role(str(item.get("step_role") or ""))
        if role == "completion":
            ok = str(item.get("outcome_key") or "")
            if ok in outcomes_seen:
                errors.append(f"Duplicate completion outcome_key: {ok}")
            outcomes_seen.add(ok)
        elif role in roles_seen:
            errors.append(f"Duplicate step_role: {role}")
        else:
            roles_seen.add(role)
    if "start" not in roles_seen:
        errors.append("Pack must include start template")
    for ok in OUTCOME_COMPLETION_KEYS:
        if ok not in outcomes_seen:
            errors.append(f"Pack must include completion template for outcome={ok}")
    for role in MIDDLE_STEP_ROLES:
        if role not in roles_seen:
            errors.append(f"Pack missing middle step_role: {role}")
    return errors


def _reference_copy_rules_block(*, instruction: str = "", purpose: str = "") -> str:
    if admin_allows_reference_copy(instruction=instruction, purpose=purpose):
        return (
            "REFERENCE COPY: Admin instruction allows reference numbers/codes/IDs — include them only as described "
            "in Admin instruction, nowhere else.\n\n"
        )
    return (
        "NO REFERENCE COPY (mandatory unless Admin instruction overrides):\n"
        "• Never use the words reference, ref, reference number, reference code, your ref, or similar in "
        "header, body, footer, or button labels.\n"
        "• {{3}} is only a survey link/URL placeholder — never describe {{3}} as a reference, code, or ID in prose.\n"
        "• Do not invent case IDs, ticket IDs, order IDs, CSAT codes, or tracking codes.\n"
        "• CTAs should say survey link, button below, open your survey — not reference number.\n\n"
    )


def _meta_buttons_rules_block() -> str:
    return (
        "BUTTONS — Meta WhatsApp template rules (strict; Telnyx will reject invalid templates):\n"
        f"• quick_reply — MIN 1, MAX {META_QUICK_REPLY_MAX_BUTTONS} buttons per template. NEVER output 4 or more.\n"
        f"  – Each button object MUST include a non-empty text field (1–{META_BUTTON_LABEL_MAX_CHARS} chars). Never leave text blank.\n"
        f"  – Each label ≤{META_BUTTON_LABEL_MAX_CHARS} characters. Plain text only (no emojis in button labels).\n"
        "  – yes_no step: exactly 2 buttons (e.g. Yes / No). abc_choice: 2–3 buttons (A / B / C).\n"
        "  – start step: usually 1 quick_reply (“Start survey”) OR use button_type url with one button.\n"
        "• url — exactly ONE button; label ≤25 chars; url MUST start with https:// (static URL in template, not {{variables}} in url field).\n"
        "• phone — exactly ONE button; label ≤25 chars; include phone_number in E.164 (e.g. +441234567890).\n"
        "• none — no buttons; set buttons to [] and button_type to none.\n"
        "• NEVER mix quick_reply with url or phone in the same template — pick one button_type only.\n"
        "• completion/thank-you templates: prefer button_type none (no CTA buttons).\n"
        "• Do not duplicate button labels within the same template.\n\n"
        "NOT ALLOWED (Meta rejects these):\n"
        "• More than 3 quick_reply buttons (even though Meta allows 10, VoxBulk caps at 3 for approval and UX).\n"
        "• Variables {{1}} in footer, header, or button labels — variables belong in BODY only.\n"
        "• URLs or emails in footer.\n"
        "• ALL CAPS body, spam phrases, false urgency, prizes, or misleading claims.\n"
        "• AUTHENTICATION category for survey invites — use MARKETING.\n"
        "• Threatening, abusive, or adult content.\n\n"
    )


def _meta_compliance_rules_block(*, privacy_mode: str = PRIVACY_MODE_OFF) -> str:
    pm = normalize_privacy_mode(privacy_mode)
    standard_footer = STANDARD_OPT_OUT_FOOTER
    anon_footer = ANONYMOUS_FOOTER
    _ = pm  # reserved for future privacy-specific Meta notes
    return (
        "META / WHATSAPP BUSINESS APPROVAL RULES (strict — violations cause Telnyx/Meta rejection):\n"
        f"• FOOTER — hard limit {META_FOOTER_MAX_CHARS} characters. Plain text only. No URLs. No {{variables}}.\n"
        f"  – Privacy Mode Off: footer MUST be exactly “{standard_footer}” ({len(standard_footer)} chars).\n"
        f"  – Privacy Mode On: footer MUST be exactly “{anon_footer}” ({len(anon_footer)} chars).\n"
        "  – NEVER put privacy policy URLs, contact emails, legal disclaimers, or PECR/GDPR paragraphs in the footer.\n"
        "  – Put privacy/data wording in the BODY instead (keep body concise).\n"
        f"• HEADER — optional; max {META_HEADER_MAX_CHARS} chars; no variables; plain text only.\n"
        f"• BODY — max {META_BODY_HARD_MAX_CHARS} chars; target ≤{META_BODY_SOFT_MAX_CHARS} for faster Meta approval.\n"
        "  Variables {{1}}, {{2}}, etc. allowed in BODY only — sequential from {{1}}.\n"
        f"{_meta_buttons_rules_block()}"
        "• CATEGORY — use MARKETING for survey invitations (not AUTHENTICATION).\n"
        "• TONE — professional UK business English: warm, clear, trustworthy. No spam triggers.\n"
        "  Avoid: ALL CAPS, false urgency, guilt-tripping, ‘ACT NOW’, ‘FREE’, or exaggerated claims.\n"
        "  Do not mention Meta, WhatsApp, OpenAI, or Telnyx in customer-facing copy.\n\n"
    )


def _emoji_rules_block() -> str:
    return (
        "EMOJIS — make templates visually appealing on WhatsApp:\n"
        f"• Use tasteful, friendly emojis in at least 8 of {PACK_SIZE} templates "
        "(e.g. 👋 ✨ 📋 ⭐ 🙏 💬 🌟 — never more than 3 per message).\n"
        "• Warm/friendly and follow-up templates should usually include 1–2 emojis.\n"
        "• Premium/professional variants may use 0–1 subtle emoji only.\n"
        "• Healthcare/clinical packs: prefer calm, reassuring tone; use emojis sparingly (0–1).\n\n"
    )


def _pack_system_prompt(
    *,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    company_name: str | None = None,
) -> str:
    privacy_mode = normalize_privacy_mode(privacy_mode)
    anonymous_block = ""
    style_mix = (
        "STYLE MIX — make all 12 feel distinct, not repetitive:\n"
        "• 2 warm/friendly (emoji-friendly, conversational)\n"
        "• 2 premium/professional (polished, trust-building, minimal emoji)\n"
        "• 2 short/direct (under ~280 chars, punchy hook)\n"
        "• 2 follow-up/reminder (gentle nudge, ‘still time to…’)\n"
        "• 2 standard identified feedback (variant_type standard)\n"
        "• 2 completion/thank-you closings with distinct tone per outcome_key\n\n"
    )
    variable_block = (
        "VARIABLES (Meta format, sequential, must appear in body/header):\n"
        "{{1}} = customer first name\n"
        "{{2}} = business/service name\n"
        "{{3}} = personal survey link (URL only — never label it a reference or code in copy)\n"
        "{{4}} = appointment or service date when relevant\n\n"
    )
    if privacy_mode == PRIVACY_MODE_ON:
        style_mix = (
            "PRIVACY MODE ON — all 12 templates must use variant_type anonymous.\n"
            "Every template must clearly state responses are anonymous and must not identify the recipient.\n"
            "STYLE MIX — make all 12 feel distinct while staying anonymous:\n"
            "• 2 warm/friendly\n"
            "• 2 premium/professional\n"
            "• 2 short/direct\n"
            "• 2 follow-up/reminder\n"
            "• 2 completion/thank-you focused\n\n"
        )
        variable_block = (
            "VARIABLES (Meta format — anonymous mode):\n"
            "Do NOT use {{1}} or any customer-name variable.\n"
            "Use only {{2}} = business/service name and {{3}} = survey link when needed.\n"
            "Never include reference numbers, case IDs, ticket IDs, order IDs, CSAT codes, or tracking codes.\n\n"
        )
        anonymous_block = (
            f"All templates: variant_type anonymous; body must include that the survey is anonymous; "
            f"footer must be exactly “{ANONYMOUS_FOOTER}”. "
            "Start/invite copy must say feedback is anonymous — never use the customer's name.\n\n"
        )
    else:
        anonymous_block = (
            "PRIVACY MODE OFF — all templates must use variant_type standard (identified/normal wording).\n"
            "Do not generate anonymous variant_type templates in this pack.\n\n"
        )

    return (
        "You are an expert WhatsApp Business template copywriter for VoxBulk customer satisfaction surveys. "
        "Write exactly 12 reusable Meta/Telnyx-compatible templates that feel native on WhatsApp — warm, mobile-first, "
        "professional, and visually polished while staying Meta approval-friendly (no spam, no ALL CAPS shouting, "
        "no false urgency). Use British English. Do not use OpenAI Realtime.\n\n"
        f"{_meta_compliance_rules_block(privacy_mode=privacy_mode)}"
        f"{anonymous_block}"
        f"{variable_block}"
        f"{_company_name_prompt_block(company_name=company_name)}"
        f"{style_mix}"
        f"{_reference_copy_rules_block(instruction=instruction, purpose=purpose)}"
        f"{_emoji_rules_block()}"
        "CTA COPY — weave in natural action phrases such as: ‘Tap below’, ‘Rate your experience’, ‘Share feedback’, "
        "‘It only takes a minute’, ‘We’d love your thoughts’. Keep sentences short and scannable on mobile.\n\n"
        "BUTTON-AWARE COPY (follow Meta limits exactly):\n"
        f"• quick_reply: 1–{META_QUICK_REPLY_MAX_BUTTONS} buttons ONLY — never 4+. Body invites a tap.\n"
        f"  Labels ≤{META_BUTTON_LABEL_MAX_CHARS} chars: ‘Start survey’, ‘Yes’, ‘No’, ‘Share feedback’.\n"
        "• url: exactly ONE button + https URL. Body directs user to tap the link button.\n"
        "• phone: exactly ONE call button. Body invites a call if needed.\n"
        "• none: buttons [] — use for rating/reason/completion steps answered by free-text reply.\n"
        "• Never combine quick_reply with url/phone in one template.\n\n"
        f"STRUCTURE: strong opening hook in first line; short paragraphs; WhatsApp-friendly length (body ≤{META_BODY_SOFT_MAX_CHARS} chars ideal). "
        f"Quick reply: never more than {META_QUICK_REPLY_MAX_BUTTONS} buttons. "
        f"Standard templates: footer exactly “{STANDARD_OPT_OUT_FOOTER}”. "
        f"Anonymous templates: body must include that the survey is anonymous; footer exactly “{ANONYMOUS_FOOTER}”. "
        "template_name: unique lowercase snake_case, no voxbulk_survey prefix.\n\n"
        "STEP BANK — return exactly 12 templates:\n"
        "• one template per middle step_role (rating, yes_no, helpfulness, abc_choice, reason, feeling_word, follow_up, improvement)\n"
        "• one start template\n"
        "• THREE completion templates — each step_role=completion with a distinct outcome_key: happy, neutral, unhappy\n"
        "start — intro with quick_reply (1 button) or url CTA (1 button) to begin the survey; "
        "include {{2}} when a company name is provided\n"
        "rating — button_type none (user replies with a score in chat)\n"
        "yes_no — quick_reply with exactly 2 buttons\n"
        "helpfulness — button_type none or quick_reply with 2–3 options\n"
        "abc_choice — quick_reply with 2 or 3 buttons (never 4+)\n"
        "reason — open follow-up asking why or what stood out\n"
        "feeling_word — pick a feeling word (great, okay, disappointing…)\n"
        "follow_up — short follow-up or reminder nudge\n"
        "improvement — what could we improve\n"
        "completion (×3) — warm thank-you closings tuned to outcome_key; each must include {{2}} when a company name is provided:\n"
        "  happy — appreciative, positive tone\n"
        "  neutral — balanced thank-you\n"
        "  unhappy — empathetic apology / support tone (no aggressive CTA)\n"
        "Each completion template MUST set outcome_key to happy, neutral, or unhappy.\n"
        "All other templates MUST set outcome_key to null (not omitted).\n"
        "Set step_role on every template. Middle roles should use standard variant unless anonymous-specific."
    )


def _pack_user_prompt(
    *,
    survey_type: SurveyType,
    industry: Industry,
    purpose: str,
    instruction: str,
    privacy_mode: str = PRIVACY_MODE_OFF,
    company_name: str | None = None,
) -> str:
    privacy_mode = normalize_privacy_mode(privacy_mode)
    is_csat = survey_type.slug in {"customer_satisfaction", "csat", "nps"} or "satisfaction" in survey_type.slug
    parts = [
        f"Industry: {industry.name}",
        f"Industry slug: {industry.slug}",
        f"Survey type: {survey_type.name}",
        f"Slug: {survey_type.slug}",
        f"Service type: {survey_type.slug}",
        f"Privacy Mode: {'On (anonymous)' if privacy_mode == PRIVACY_MODE_ON else 'Off (identified)'}",
        f"Description: {survey_type.description or survey_type.name}",
        f"Supports anonymous: {bool(survey_type.supports_anonymous)}",
    ]
    parts.append(
        f"Write all copy for the {industry.name} industry — tone, examples, and wording must fit this vertical."
    )
    company = str(company_name or "").strip()
    if company:
        parts.append(
            f"Company / business name from profile: {company}. "
            "Use Meta placeholder {{2}} for this name on the start screen and on all three completion screens only."
        )
    else:
        parts.append(
            "Company / business name: not set in profile — omit {{2}} everywhere; use neutral wording without naming a business."
        )
    if is_csat:
        parts.append(
            "Pack focus: customer satisfaction / post-service feedback for UK businesses. "
            "Templates should help collect honest ratings after a visit, call, or delivery. "
            "Sound human — like a friendly team member, not a corporate mail merge."
        )
    if purpose.strip():
        parts.append(f"Template purpose focus: {purpose.strip()}")
    if instruction.strip():
        parts.append(f"Admin instruction: {instruction.strip()}")
    parts.append(
        f"Generate exactly {PACK_SIZE} visually attractive, conversational, persuasive WhatsApp templates as JSON. "
        "Include one template per middle step_role, one start, and three completion templates "
        "(outcome_key happy, neutral, unhappy). No duplicate non-completion step_roles."
    )
    return "\n".join(parts)


def _single_template_system_prompt(
    *,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    company_name: str | None = None,
) -> str:
    return (
        _pack_system_prompt(
            privacy_mode=privacy_mode,
            instruction=instruction,
            purpose=purpose,
            company_name=company_name,
        )
        + "\n\nYou are regenerating ONE template slot. Return JSON with a single `template` object. "
        "Make it noticeably better, more WhatsApp-native, emoji-friendly where appropriate, and more button-aware "
        "than a generic draft. Never add reference/ref wording unless Admin instruction explicitly requires it."
    )


def _single_template_user_prompt(
    *,
    survey_type: SurveyType,
    industry: Industry,
    purpose: str,
    instruction: str,
    slot_hint: str,
    current_template: dict[str, Any] | None,
    sibling_summaries: list[dict[str, Any]] | None,
    privacy_mode: str = PRIVACY_MODE_OFF,
    company_name: str | None = None,
) -> str:
    parts = [
        _pack_user_prompt(
            survey_type=survey_type,
            industry=industry,
            purpose=purpose,
            instruction=instruction,
            privacy_mode=privacy_mode,
            company_name=company_name,
        )
    ]
    if slot_hint.strip():
        parts.append(f"Slot/style to preserve: {slot_hint.strip()}")
    if current_template:
        parts.append(
            "Replace this draft with a stronger version (same variant_type and button_type unless instruction says otherwise):\n"
            f"- template_name: {current_template.get('template_name')}\n"
            f"- purpose: {current_template.get('purpose')}\n"
            f"- variant_type: {current_template.get('variant_type')}\n"
            f"- button_type: {current_template.get('button_type')}\n"
            f"- body: {current_template.get('body')}\n"
            f"- footer: {current_template.get('footer')}"
        )
    siblings = sibling_summaries or []
    if siblings:
        lines = [f"  • {s.get('template_name')}: {s.get('purpose')} — {(s.get('body') or '')[:100]}" for s in siblings[:8]]
        parts.append("Do not duplicate these sibling templates:\n" + "\n".join(lines))
    parts.append("Return one improved template as JSON.")
    return "\n\n".join(parts)


def _build_pack_item_row(
    db: Session,
    *,
    survey_type: SurveyType,
    idx: int,
    item: dict[str, Any],
    seen_names: set[str],
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    company_name: str | None = None,
) -> dict[str, Any]:
    coerced = coerce_meta_template_fields(item, privacy_mode=privacy_mode)
    normalized, errors = validate_generated_template(
        coerced,
        survey_type=survey_type,
        privacy_mode=privacy_mode,
        instruction=instruction,
        purpose=purpose,
        company_name=company_name,
        apply_company_name_rules=True,
    )
    row: dict[str, Any] = {
        "index": idx,
        "raw": item,
        "valid": not errors,
        "errors": errors,
    }
    if not normalized:
        return row
    name_key = normalized["template_name"]
    if name_key in seen_names:
        dup = errors + [f"duplicate template_name {name_key}"]
        row["valid"] = False
        row["errors"] = dup
        return row
    seen_names.add(name_key)
    telnyx_name = _ensure_unique_telnyx_name(db, _telnyx_pack_name(survey_type.slug, normalized["template_name"]))
    preview_business = (
        normalized["example_values"][1]
        if len(normalized["example_values"]) > 1 and str(normalized["example_values"][1] or "").strip()
        else (str(company_name or "").strip() or "Your business")
    )
    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        _preview_row(normalized, telnyx_name),
        first_name=normalized["example_values"][0] if normalized["example_values"] else "Alex",
        business_name=preview_business,
    )
    row["template"] = {
        **normalized,
        "telnyx_name": telnyx_name,
        "display_name": normalized["title"],
        "preview": preview,
        "buttons_preview": preview.get("buttons") or [],
    }
    return row


class SurveyWaTemplatePackService:
    @staticmethod
    def generate_pack(
        db: Session,
        *,
        survey_type: SurveyType,
        purpose: str = "",
        instruction: str = "",
        privacy_mode: str = PRIVACY_MODE_OFF,
        theme_variant: str = "",
        template_count: int = PACK_SIZE,
        industry_id: str | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        privacy_mode = normalize_privacy_mode(privacy_mode)
        company_name = resolve_wa_survey_company_name(db, org_id=org_id)
        try:
            industry = load_industry_for_prompt(db, survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if industry_id and str(industry_id).strip() != industry.id:
            raise SurveyWaTemplatePackError("Industry does not match survey type")
        try:
            raw, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=_pack_system_prompt(
                    privacy_mode=privacy_mode,
                    instruction=instruction,
                    purpose=purpose,
                    company_name=company_name,
                ),
                user_prompt=_pack_user_prompt(
                    survey_type=survey_type,
                    industry=industry,
                    purpose=purpose,
                    instruction=instruction,
                    privacy_mode=privacy_mode,
                    company_name=company_name,
                ),
                json_schema=WA_TEMPLATE_PACK_JSON_SCHEMA,
                schema_name="wa_survey_template_pack",
                max_output_tokens=16000,
                temperature=0.68,
            )
        except ValueError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        except httpx.TimeoutException as e:
            raise SurveyWaTemplatePackError(
                "OpenAI took too long to generate the template pack. Please try again — "
                "10-template packs can take 2–5 minutes."
            ) from e

        items = raw.get("templates")
        if not isinstance(items, list):
            raise SurveyWaTemplatePackError("OpenAI response missing templates array")

        validated: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for idx, item in enumerate(items):
            row = _build_pack_item_row(
                db,
                survey_type=survey_type,
                idx=idx,
                item=item,
                seen_names=seen_names,
                privacy_mode=privacy_mode,
                instruction=instruction,
                purpose=purpose,
                company_name=company_name,
            )
            if row.get("valid") and row.get("template"):
                validated.append(row)
            else:
                invalid.append(row)

        composition_errors = _validate_pack_composition(
            [r["template"] for r in validated if r.get("template")]
        )

        return {
            "ok": True,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "company_name": company_name,
            "survey_type_id": survey_type.id,
            "survey_type_name": survey_type.name,
            "service_type": survey_type.slug,
            "privacy_mode": privacy_mode,
            "theme_variant": str(theme_variant or "").strip() or None,
            "template_count": int(template_count or PACK_SIZE),
            "generated_count": len(items),
            "valid_count": len(validated),
            "invalid_count": len(invalid),
            "templates": validated + invalid,
            "valid_templates": [r["template"] for r in validated if r.get("template")],
            "composition_errors": composition_errors,
            "composition_ok": not composition_errors,
            "openai": meta,
        }

    @staticmethod
    def regenerate_pack_item(
        db: Session,
        *,
        survey_type: SurveyType,
        index: int,
        purpose: str = "",
        instruction: str = "",
        slot_hint: str = "",
        current_template: dict[str, Any] | None = None,
        sibling_summaries: list[dict[str, Any]] | None = None,
        seen_names: list[str] | None = None,
        privacy_mode: str = PRIVACY_MODE_OFF,
        industry_id: str | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        privacy_mode = normalize_privacy_mode(
            privacy_mode or (current_template or {}).get("privacy_mode") or PRIVACY_MODE_OFF
        )
        company_name = resolve_wa_survey_company_name(db, org_id=org_id)
        try:
            industry = load_industry_for_prompt(db, survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if industry_id and str(industry_id).strip() != industry.id:
            raise SurveyWaTemplatePackError("Industry does not match survey type")
        try:
            raw, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=_single_template_system_prompt(
                    privacy_mode=privacy_mode,
                    instruction=instruction,
                    purpose=purpose,
                    company_name=company_name,
                ),
                user_prompt=_single_template_user_prompt(
                    survey_type=survey_type,
                    industry=industry,
                    purpose=purpose,
                    instruction=instruction,
                    slot_hint=slot_hint,
                    current_template=current_template,
                    sibling_summaries=sibling_summaries,
                    privacy_mode=privacy_mode,
                    company_name=company_name,
                ),
                json_schema=WA_SINGLE_TEMPLATE_JSON_SCHEMA,
                schema_name="wa_survey_template_single",
                max_output_tokens=4000,
                temperature=0.72,
            )
        except ValueError as e:
            raise SurveyWaTemplatePackError(str(e)) from e

        item = raw.get("template")
        if not isinstance(item, dict):
            raise SurveyWaTemplatePackError("OpenAI response missing template object")

        names = {str(n) for n in (seen_names or []) if str(n).strip()}
        if current_template and current_template.get("template_name"):
            names.discard(str(current_template["template_name"]))
        row = _build_pack_item_row(
            db,
            survey_type=survey_type,
            idx=int(index),
            item=item,
            seen_names=names,
            privacy_mode=privacy_mode,
            instruction=instruction,
            purpose=purpose,
            company_name=company_name,
        )
        return {
            "ok": True,
            "item": row,
            "openai": meta,
            "privacy_mode": privacy_mode,
            "company_name": company_name,
        }

    @staticmethod
    def _upsert_or_create_draft_row(
        db: Session,
        *,
        survey_type: SurveyType,
        item: dict[str, Any],
        pack_id: str | None,
        privacy_mode: str,
    ) -> TelnyxWhatsappTemplate:
        from app.services.survey_type_template_service import template_belongs_to_survey_type

        raw_id = item.get("id") or item.get("template_id")
        if raw_id is not None:
            try:
                template_id = int(raw_id)
            except (TypeError, ValueError):
                template_id = 0
            if template_id > 0:
                row = db.get(TelnyxWhatsappTemplate, template_id)
                if row is not None and template_belongs_to_survey_type(row, survey_type):
                    components = item.get("components")
                    if not isinstance(components, list) or not components:
                        components = build_components_from_generated(item)
                    SurveyWhatsappTemplateService.save_draft(
                        db,
                        row,
                        {
                            "display_name": item.get("title") or item.get("template_name"),
                            "components": components,
                            "category": item.get("category"),
                            "example_values": item.get("example_values"),
                        },
                    )
                    row.step_role = str(item.get("step_role") or "")[:32] or None
                    outcome_key = str(item.get("outcome_key") or "").strip().lower() or None
                    row.outcome_key = outcome_key
                    row.pack_id = pack_id or row.pack_id
                    row.privacy_mode = privacy_mode
                    row.variant_type = privacy_mode_to_variant(privacy_mode)
                    apply_industry_to_template(row, survey_type)
                    db.add(row)
                    db.flush()
                    pm = privacy_mode
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

        return SurveyWaTemplatePackService._create_draft_row(
            db,
            survey_type=survey_type,
            item=item,
            pack_id=pack_id,
            privacy_mode=privacy_mode,
        )

    @staticmethod
    def save_selected_templates(
        db: Session,
        *,
        survey_type: SurveyType,
        templates: list[dict[str, Any]],
        privacy_mode: str = PRIVACY_MODE_OFF,
        theme_variant: str = "",
        purpose: str = "",
        instruction: str = "",
        industry_id: str | None = None,
        replace_step_bank: bool = False,
    ) -> dict[str, Any]:
        if not templates:
            raise SurveyWaTemplatePackError("Select at least one template to save")

        try:
            industry_id_resolved = resolve_survey_type_industry_id(survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if industry_id and str(industry_id).strip() != industry_id_resolved:
            raise SurveyWaTemplatePackError("Industry does not match survey type")

        privacy_mode = normalize_privacy_mode(
            privacy_mode or (templates[0] or {}).get("privacy_mode") or PRIVACY_MODE_OFF
        )
        pack = SurveyTemplatePack(
            id=str(uuid.uuid4()),
            industry_id=industry_id_resolved,
            survey_type_id=survey_type.id,
            privacy_mode=privacy_mode,
            template_count=len(templates),
            service_type=str(survey_type.slug or ""),
            theme_variant=str(theme_variant or "").strip() or None,
            purpose=str(purpose or "").strip() or None,
            instruction=str(instruction or "").strip() or None,
            created_at=_now(),
        )
        db.add(pack)
        db.flush()

        saved: list[dict[str, Any]] = []
        errors: list[str] = []
        for item in templates:
            item = coerce_meta_template_fields({**item, "privacy_mode": privacy_mode}, privacy_mode=privacy_mode)
            normalized, val_errors = validate_generated_template(
                item,
                survey_type=survey_type,
                privacy_mode=privacy_mode,
                instruction=instruction,
                purpose=purpose,
            )
            if not normalized:
                errors.append(f"{item.get('template_name') or 'template'}: {'; '.join(val_errors)}")
                continue
            try:
                row = SurveyWaTemplatePackService._upsert_or_create_draft_row(
                    db,
                    survey_type=survey_type,
                    item={**normalized, "id": item.get("id") or item.get("template_id")},
                    pack_id=pack.id,
                    privacy_mode=privacy_mode,
                )
                saved.append(survey_template_to_dict(row, linked_survey_type_count=1))
            except SurveyWhatsappTemplateError as e:
                errors.append(str(e))

        if not saved and errors:
            db.rollback()
            raise SurveyWaTemplatePackError("; ".join(errors[:5]))

        saved_ids = [int(t["id"]) for t in saved if t.get("id")]
        if replace_step_bank and saved_ids:
            SurveyTypeTemplateService.prune_stale_step_bank_mappings(
                db,
                survey_type_id=survey_type.id,
                keep_template_ids=saved_ids,
                privacy_mode=privacy_mode,
            )

        db.commit()

        return {
            "ok": True,
            "pack_id": pack.id,
            "industry_id": industry_id_resolved,
            "privacy_mode": privacy_mode,
            "saved_count": len(saved),
            "templates": saved,
            "errors": errors[:20],
        }

    @staticmethod
    def _create_draft_row(
        db: Session,
        *,
        survey_type: SurveyType,
        item: dict[str, Any],
        pack_id: str | None = None,
        privacy_mode: str = PRIVACY_MODE_OFF,
    ) -> TelnyxWhatsappTemplate:
        components = item.get("components")
        if not isinstance(components, list) or not components:
            components = build_components_from_generated(item)
        examples = item.get("example_values")
        if not isinstance(examples, list) or not examples:
            examples = _extract_example_values(components)

        telnyx_name = _ensure_unique_telnyx_name(
            db, _telnyx_pack_name(survey_type.slug, item["template_name"])
        )
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        privacy_mode = normalize_privacy_mode(item.get("privacy_mode") or privacy_mode)
        variant = privacy_mode_to_variant(privacy_mode)
        outcome_key = str(item.get("outcome_key") or "")[:16] or None
        outcome_vars = item.get("outcome_variables")
        if outcome_key and not outcome_vars:
            from app.services.survey_outcome_template_service import default_outcome_variables

            outcome_vars = default_outcome_variables(outcome_key)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name=telnyx_name,
            display_name=str(item.get("title") or item.get("template_name"))[:128],
            step_role=str(item.get("step_role") or "")[:32] or None,
            outcome_key=outcome_key,
            outcome_variables_json=_dumps(outcome_vars) if outcome_vars else None,
            language=str(item.get("language") or "en_US"),
            category=_normalize_category(item.get("category")),
            status="LOCAL_DRAFT",
            variant_type=variant,
            privacy_mode=privacy_mode,
            pack_id=pack_id,
            industry_id=resolve_survey_type_industry_id(survey_type),
            survey_type_id=survey_type.id,
            body_preview=_body_preview(components),
            draft_components_json=_dumps(components),
            example_values_json=_dumps([str(v) for v in examples]),
            local_sync_status=SYNC_DRAFT,
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        apply_industry_to_template(row, survey_type)

        if variant == VARIANT_ANONYMOUS:
            SurveyTypeTemplateService.upsert_mapping(
                db,
                survey_type_id=survey_type.id,
                template_id=row.id,
                usable_as_anonymous=True,
                privacy_mode=PRIVACY_MODE_ON,
            )
        else:
            SurveyTypeTemplateService.upsert_mapping(
                db,
                survey_type_id=survey_type.id,
                template_id=row.id,
                usable_as_standard=True,
                privacy_mode=PRIVACY_MODE_OFF,
            )
        db.refresh(row)
        return row


def _preview_row(item: dict[str, Any], telnyx_name: str) -> TelnyxWhatsappTemplate:
    """Ephemeral row for preview rendering only (not persisted)."""
    components = item.get("components") or build_components_from_generated(item)
    examples = item.get("example_values") or _extract_example_values(components)
    return TelnyxWhatsappTemplate(
        telnyx_record_id="preview",
        template_id="preview",
        name=telnyx_name,
        display_name=str(item.get("title") or item.get("template_name"))[:128],
        language=str(item.get("language") or "en_US"),
        category=_normalize_category(item.get("category")),
        status="LOCAL_DRAFT",
        variant_type=str(item.get("variant_type") or VARIANT_STANDARD),
        draft_components_json=_dumps(components),
        example_values_json=_dumps(examples),
        local_sync_status=SYNC_DRAFT,
        active_for_survey=True,
    )
