"""Generate reusable WhatsApp survey template packs via OpenAI Responses API."""

from __future__ import annotations

import json
import re
import uuid
import copy
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
from app.services.survey_step_bank_service import (
    ALL_STEP_ROLES,
    MIDDLE_STEP_ROLES,
    PACK_STEP_ROLES,
    normalize_step_role,
)
from app.services.survey_wa_vague_negative_followup_service import (
    attach_auto_followup_to_template_item,
    normalize_template_example_values,
)
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
    _normalize_draft_components,
    _now,
    build_meta_body_component,
    survey_template_to_dict,
)

_FOOTER_URL_RE = re.compile(r"https?://", re.I)
_FOOTER_VAR_RE = re.compile(r"\{\{\d+\}\}")

# Middle library templates — welcome is sent separately via Global System Templates.
_LIBRARY_MIDDLE_VAR_RE = re.compile(r"\{\{\d+\}\}")
_LIBRARY_GREETING_PREFIX_RE = re.compile(
    r"^(?:\s*(?:hi|hello|hey|dear)\s*(?:\{\{1\}\}|there|customer)?\s*[,!.:-]?\s*)+",
    re.IGNORECASE,
)
_LIBRARY_OPENING_PHRASE_RE = re.compile(
    r"\b("
    r"thanks for booking|"
    r"thank you for booking|"
    r"thanks for (?:visiting|choosing|dining|contacting|your visit)|"
    r"welcome to|"
    r"we(?:'|’)d love (?:your|to hear)|"
    r"before we (?:start|begin)|"
    r"(?:this|a) (?:short|quick) survey|"
    r"let(?:'|’)s (?:start|begin)"
    r")\b",
    re.IGNORECASE,
)
_LIBRARY_BUTTON_STEP_ROLES = frozenset({"rating", "yes_no", "helpfulness", "abc_choice", "feeling_word"})
_LIBRARY_TEXT_ONLY_STEP_ROLES = frozenset({"reason", "follow_up", "improvement"})

BULK_LIBRARY_MIDDLE_INSTRUCTION = (
    "MIDDLE SURVEY STEP ONLY — the welcome/opening message was already sent from Global System Templates. "
    "Do NOT greet again. Do NOT use Hi {{1}} or any name variable. Do NOT say thanks for booking/visiting. "
    "Do NOT welcome the user or explain that a survey is starting. Ask one in-flow question only."
)


def library_template_button_defaults(step_role: str) -> tuple[str, list[dict[str, Any]]]:
    """Meta-safe quick_reply defaults for bulk library middle steps (max 3 buttons)."""
    role = normalize_step_role(step_role)
    empty = {"url": "", "phone_number": ""}
    if role == "rating":
        return "quick_reply", [
            {"text": "Poor", **empty},
            {"text": "Okay", **empty},
            {"text": "Excellent", **empty},
        ]
    if role == "yes_no":
        return "quick_reply", [{"text": "Yes", **empty}, {"text": "No", **empty}]
    if role == "helpfulness":
        return "quick_reply", [
            {"text": "Very helpful", **empty},
            {"text": "Partly helpful", **empty},
            {"text": "Not helpful", **empty},
        ]
    if role == "abc_choice":
        return "quick_reply", [
            {"text": "Option A", **empty},
            {"text": "Option B", **empty},
            {"text": "Option C", **empty},
        ]
    if role == "feeling_word":
        return "quick_reply", [
            {"text": "Great", **empty},
            {"text": "Okay", **empty},
            {"text": "Poor", **empty},
        ]
    return "none", []


def validate_library_middle_step_copy(*, body: str, header: str = "", step_role: str = "") -> list[str]:
    """Reject opening/welcome phrasing in bulk library middle-step templates."""
    errors: list[str] = []
    combined = f"{header} {body}".strip()
    if not combined:
        errors.append("body is required")
        return errors
    if _LIBRARY_MIDDLE_VAR_RE.search(combined):
        errors.append("middle library templates must not use {{variables}} — welcome already personalises separately")
    if _LIBRARY_GREETING_PREFIX_RE.match(body.strip()):
        errors.append("middle library templates must not start with a greeting (Hi/Hello/Hey)")
    if _LIBRARY_OPENING_PHRASE_RE.search(combined):
        errors.append(
            "middle library templates must not use opening/outreach copy (thanks for booking, welcome, survey intro)"
        )
    if re.search(r"\breply with (?:a )?(?:number|score|1)\b", combined, re.I):
        errors.append("do not ask users to reply with a number — use quick_reply buttons when supported")
    role = normalize_step_role(step_role)
    if role in _LIBRARY_BUTTON_STEP_ROLES and re.search(r"\bfrom 1 to 5\b", combined, re.I):
        errors.append("rating questions must use quick_reply buttons, not a 1–5 free-text prompt")
    return errors


def normalize_library_middle_template(item: dict[str, Any], *, step_role: str) -> dict[str, Any]:
    """Coerce OpenAI output toward middle-step library shape (no greeting vars, role-aware buttons)."""
    out = dict(item)
    role = normalize_step_role(step_role or out.get("step_role") or "")
    body = str(out.get("body") or "").strip()
    header = str(out.get("header") or "").strip()

    body = _LIBRARY_GREETING_PREFIX_RE.sub("", body).strip()
    body = re.sub(
        r"thanks for (?:booking|visiting|choosing|dining|contacting)[^.!?]*[.!?]\s*",
        "",
        body,
        flags=re.IGNORECASE,
    ).strip()
    body = re.sub(r",?\s*from 1 to 5\??", "?", body, flags=re.IGNORECASE).strip()
    body = re.sub(r"\breply with (?:a )?(?:number|score|rating)\b[^.?!]*[.?!]?\s*", "", body, flags=re.IGNORECASE).strip()
    body = _LIBRARY_MIDDLE_VAR_RE.sub("", body)
    body = re.sub(r"\s{2,}", " ", body).strip(" ,.;:-")

    out["header"] = ""
    out["body"] = body
    out["example_values"] = []
    out = normalize_template_example_values(out)

    if role in _LIBRARY_BUTTON_STEP_ROLES:
        button_type, buttons = library_template_button_defaults(role)
        out["button_type"] = button_type
        existing = out.get("buttons") if isinstance(out.get("buttons"), list) else []
        labels = [
            str(b.get("text") or "").strip()
            for b in existing
            if isinstance(b, dict) and str(b.get("text") or "").strip()
        ]
        if len(labels) >= 2:
            out["buttons"] = existing[:META_QUICK_REPLY_MAX_BUTTONS]
        else:
            out["buttons"] = buttons
    elif role in _LIBRARY_TEXT_ONLY_STEP_ROLES:
        out["button_type"] = "none"
        out["buttons"] = []

    out["step_role"] = role
    out["outcome_key"] = None
    return out


def _library_middle_step_copy_rules_block() -> str:
    max_btn = META_QUICK_REPLY_MAX_BUTTONS
    return (
        "MIDDLE-STEP COPY (mandatory — NOT an opening template):\n"
        "• The welcome/opening message is sent separately from Global System Templates.\n"
        "• Do NOT start with Hi/Hello/Hey or use {{1}} / {{2}} / {{3}} anywhere.\n"
        "• Do NOT say thanks for booking/visiting, welcome, or that a survey is starting.\n"
        "• Do NOT repeat outreach/intro context — ask one in-flow question only.\n"
        "• Keep the body short (often one sentence), professional, industry-specific.\n"
        "• Light emoji allowed (0–2), e.g. ⭐ — never more than 2.\n\n"
        "BUTTONS (Meta max 3 quick_reply buttons — never 4+):\n"
        f"• rating — quick_reply with exactly 3 scale labels (e.g. Poor / Okay / Excellent). "
        "Do NOT ask to reply with a number or use a 1–5 free-text prompt.\n"
        "• yes_no — quick_reply: Yes / No (2 buttons).\n"
        "• helpfulness — quick_reply: Very helpful / Partly helpful / Not helpful (3 buttons).\n"
        "• abc_choice — quick_reply: 2–3 meaningful text labels (not A/B/C unless industry-appropriate).\n"
        "• feeling_word — quick_reply: 2–3 feeling labels (e.g. Great / Okay / Poor).\n"
        "• reason, follow_up, improvement — button_type none; short neutral question, no greeting.\n\n"
        f"All quick_reply templates: 1–{max_btn} text-only buttons. Body invites a tap below.\n\n"
        "GOOD middle-step examples:\n"
        "• “How would you rate your booking experience? ⭐”\n"
        "• “How was the food quality on your visit? ⭐”\n"
        "• “Was the work explained clearly?” (yes_no with Yes/No buttons)\n\n"
        "BAD (never generate):\n"
        "• “Hi {{1}}, thanks for booking with us. How would you rate… from 1 to 5?”\n"
    )


PACK_SIZE = 12
DEFAULT_PACK_COUNT = 5
MIN_PACK_COUNT = 1
MAX_PACK_COUNT = 50

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
    _fill_example_values(out)
    return out


def _fill_example_values(out: dict[str, Any]) -> None:
    """Ensure Meta sample values exist for validation and preview when variables are used."""
    header = str(out.get("header") or "").strip()
    body = str(out.get("body") or "").strip()
    var_ids = _var_re_from_text(f"{header} {body}")
    if not var_ids:
        out["example_values"] = []
        return

    normalized = normalize_template_example_values(out)
    examples = [str(v) for v in (normalized.get("example_values") or []) if str(v).strip()]
    if len(examples) < max(var_ids):
        defaults = {1: "Alex", 2: "Northgate Dental", 3: "https://example.com/survey"}
        padded = list(examples)
        while len(padded) < max(var_ids):
            padded.append(defaults.get(len(padded) + 1, "Guest"))
        examples = padded
    out["example_values"] = examples


OUTCOME_COMPLETION_KEYS = ("happy", "neutral", "unhappy")
PACK_MODE_SURVEY_QUESTIONS = "survey_questions"
PACK_MODE_FULL_STEP_BANK = "full_step_bank"
DEFAULT_PACK_MODE = PACK_MODE_SURVEY_QUESTIONS


def normalize_pack_mode(raw: str | None) -> str:
    mode = str(raw or DEFAULT_PACK_MODE).strip().lower()
    if mode in {PACK_MODE_SURVEY_QUESTIONS, "questions", "middle", "library"}:
        return PACK_MODE_SURVEY_QUESTIONS
    if mode in {PACK_MODE_FULL_STEP_BANK, "full", "step_bank", "full_pack"}:
        return PACK_MODE_FULL_STEP_BANK
    return DEFAULT_PACK_MODE


def clamp_pack_count(raw: int | str | None) -> int:
    if raw is None or raw == "":
        value = DEFAULT_PACK_COUNT
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_PACK_COUNT
    return max(MIN_PACK_COUNT, min(MAX_PACK_COUNT, value))


def pack_slot_plan(count: int) -> list[dict[str, Any]]:
    """Build required step_role slots for a pack of the given size."""
    from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES

    count = clamp_pack_count(count)
    slots: list[dict[str, Any]] = [{"step_role": "start"}]
    if count <= 1:
        return slots
    completions = min(len(OUTCOME_COMPLETION_KEYS), count - 1)
    middle_count = max(0, count - 1 - completions)
    for i in range(middle_count):
        slots.append({"step_role": MIDDLE_STEP_ROLES[i % len(MIDDLE_STEP_ROLES)]})
    for outcome_key in OUTCOME_COMPLETION_KEYS[:completions]:
        slots.append({"step_role": "completion", "outcome_key": outcome_key})
    return slots


def survey_question_slot_plan(count: int) -> list[dict[str, Any]]:
    """Middle-step survey question slots only — no start invite or completion thank-you."""
    count = clamp_pack_count(count)
    return [{"step_role": MIDDLE_STEP_ROLES[i % len(MIDDLE_STEP_ROLES)]} for i in range(count)]


def pack_slot_plan_for_mode(count: int, *, pack_mode: str = DEFAULT_PACK_MODE) -> list[dict[str, Any]]:
    if normalize_pack_mode(pack_mode) == PACK_MODE_SURVEY_QUESTIONS:
        return survey_question_slot_plan(count)
    return pack_slot_plan(count)


def build_pack_json_schema(count: int) -> dict[str, Any]:
    size = clamp_pack_count(count)
    return {
        "type": "object",
        "properties": {
            "templates": {
                "type": "array",
                "items": copy.deepcopy(_PACK_TEMPLATE_ITEM_SCHEMA),
                "minItems": size,
                "maxItems": size,
            }
        },
        "required": ["templates"],
        "additionalProperties": False,
    }


def build_system_template_json_schema(
    count: int,
    *,
    step_roles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Strict OpenAI Responses schema for global system-template generation."""
    size = max(1, min(int(count or 1), 6))
    schema = build_pack_json_schema(size)
    if step_roles:
        items = schema.get("properties", {}).get("templates", {}).get("items")
        if isinstance(items, dict):
            step_role = items.get("properties", {}).get("step_role")
            if isinstance(step_role, dict):
                step_role["enum"] = list(step_roles)
    assert_openai_strict_json_schema(schema)
    return schema


def assert_openai_strict_json_schema(node: Any, *, path: str = "schema") -> None:
    """Validate OpenAI Responses strict json_schema object rules before calling the API."""
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "object":
        if node.get("additionalProperties") is not False:
            raise ValueError(
                f"OpenAI strict schema invalid at {path}: additionalProperties must be false"
            )
        properties = node.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"OpenAI strict schema invalid at {path}: properties must be an object")
        required = node.get("required")
        if not isinstance(required, list) or set(required) != set(properties.keys()):
            raise ValueError(
                f"OpenAI strict schema invalid at {path}: required must list every property key"
            )
        for key, child in properties.items():
            assert_openai_strict_json_schema(child, path=f"{path}.{key}")
    elif node_type == "array":
        items = node.get("items")
        if isinstance(items, dict):
            assert_openai_strict_json_schema(items, path=f"{path}.items")
    if isinstance(node.get("anyOf"), list):
        for idx, child in enumerate(node["anyOf"]):
            if isinstance(child, dict):
                assert_openai_strict_json_schema(child, path=f"{path}.anyOf[{idx}]")


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
    from app.services.survey_wa_template_cleanup_service import WA_TEMPLATE_DEFAULT_CATEGORY

    cat = str(raw or WA_TEMPLATE_DEFAULT_CATEGORY).strip().upper()
    return cat if cat in {"MARKETING", "UTILITY", "AUTHENTICATION"} else WA_TEMPLATE_DEFAULT_CATEGORY


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
    var_ids = _var_re_from_text(f"{header} {body}")
    examples = [str(v) for v in (item.get("example_values") or []) if str(v).strip()]
    if not examples and var_ids:
        examples = ["Alex", "Northgate Dental", "https://example.com/s/abc", "Monday 9am"]

    if header:
        components.append({"type": "HEADER", "format": "TEXT", "text": header[:60]})

    body_component = build_meta_body_component(body, example_values=examples if var_ids else None)
    components.append(body_component)
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
    if var_ids:
        if not examples:
            errors.append("example_values must include at least one value for templates with variables")
        elif len(examples) < max(var_ids):
            errors.append(f"example_values must include at least {max(var_ids)} value(s) for used variables")
    elif examples and any(str(v).lower() == "sample" for v in examples):
        errors.append('example_values must not use placeholder "sample" when no variables are present')

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


def _validate_pack_composition(
    items: list[dict[str, Any]],
    *,
    template_count: int = PACK_SIZE,
    pack_mode: str = DEFAULT_PACK_MODE,
) -> list[str]:
    """Validate pack matches the requested template count and slot plan."""
    mode = normalize_pack_mode(pack_mode)
    count = clamp_pack_count(template_count)
    errors: list[str] = []
    if len(items) != count:
        errors.append(f"Expected {count} templates, got {len(items)}")
    plan = pack_slot_plan_for_mode(count, pack_mode=mode)
    if mode == PACK_MODE_SURVEY_QUESTIONS:
        roles_seen: set[str] = set()
        for idx, slot in enumerate(plan):
            if idx >= len(items):
                errors.append(f"Missing template for slot {idx + 1}")
                continue
            item = items[idx]
            role = normalize_step_role(str(item.get("step_role") or ""))
            expected_role = slot["step_role"]
            if role != expected_role:
                errors.append(f"Template {idx + 1} should be step_role={expected_role}, got {role}")
            if role in ("start", "completion"):
                errors.append(f"Template {idx + 1} must not be step_role={role} in survey question mode")
            if role in roles_seen:
                errors.append(f"Duplicate step_role in pack: {role}")
            roles_seen.add(role)
            if str(item.get("outcome_key") or "").strip():
                errors.append(f"Template {idx + 1} must not set outcome_key in survey question mode")
            lib_errors = validate_library_middle_step_copy(
                body=str(item.get("body") or ""),
                header=str(item.get("header") or ""),
                step_role=role,
            )
            for line in lib_errors:
                errors.append(f"Template {idx + 1}: {line}")
            button_labels = [
                str(b.get("text") or "").strip().lower()
                for b in (item.get("buttons") or [])
                if isinstance(b, dict)
            ]
            if any(label in {"start survey", "start", "begin survey"} for label in button_labels):
                errors.append(f"Template {idx + 1} must not use a Start survey button")
        return errors

    if count == PACK_SIZE:
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

    for idx, slot in enumerate(plan):
        if idx >= len(items):
            errors.append(f"Missing template for slot {idx + 1}")
            continue
        item = items[idx]
        role = normalize_step_role(str(item.get("step_role") or ""))
        expected_role = slot["step_role"]
        if role != expected_role:
            errors.append(f"Template {idx + 1} should be step_role={expected_role}, got {role}")
        if expected_role == "completion":
            ok = str(item.get("outcome_key") or "")
            if ok != slot.get("outcome_key"):
                errors.append(
                    f"Template {idx + 1} completion should have outcome_key={slot.get('outcome_key')}"
                )
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
        "• AUTHENTICATION category for survey invites — use UTILITY.\n"
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
        "• CATEGORY — use UTILITY for survey invitations (not AUTHENTICATION).\n"
        "• TONE — professional UK business English: warm, clear, trustworthy. No spam triggers.\n"
        "  Avoid: ALL CAPS, false urgency, guilt-tripping, ‘ACT NOW’, ‘FREE’, or exaggerated claims.\n"
        "  Do not mention Meta, WhatsApp, OpenAI, or Telnyx in customer-facing copy.\n\n"
    )


def _emoji_rules_block(*, template_count: int = PACK_SIZE) -> str:
    emoji_target = max(1, min(template_count, 8))
    return (
        "EMOJIS — make templates visually appealing on WhatsApp:\n"
        f"• Use tasteful, friendly emojis in at least {emoji_target} of {template_count} templates "
        "(e.g. 👋 ✨ 📋 ⭐ 🙏 💬 🌟 — never more than 3 per message).\n"
        "• Warm/friendly and follow-up templates should usually include 1–2 emojis.\n"
        "• Premium/professional variants may use 0–1 subtle emoji only.\n"
        "• Healthcare/clinical packs: prefer calm, reassuring tone; use emojis sparingly (0–1).\n\n"
    )


def _pack_structure_block(*, template_count: int = PACK_SIZE) -> str:
    count = clamp_pack_count(template_count)
    if count == PACK_SIZE:
        return (
            "STEP BANK — return exactly 12 templates:\n"
            "• one template per middle step_role (rating, yes_no, helpfulness, abc_choice, reason, feeling_word, follow_up, improvement)\n"
            "• one start template\n"
            "• THREE completion templates — each step_role=completion with a distinct outcome_key: happy, neutral, unhappy\n"
        )
    plan = pack_slot_plan(count)
    lines = [f"STEP BANK — return exactly {count} templates in this order:"]
    for idx, slot in enumerate(plan, start=1):
        if slot["step_role"] == "completion":
            lines.append(
                f"  {idx}. step_role=completion, outcome_key={slot.get('outcome_key')}"
            )
        else:
            lines.append(f"  {idx}. step_role={slot['step_role']}")
    return "\n".join(lines) + "\n"


def _survey_questions_structure_block(*, template_count: int = DEFAULT_PACK_COUNT) -> str:
    count = clamp_pack_count(template_count)
    plan = survey_question_slot_plan(count)
    lines = [
        f"SURVEY QUESTIONS — return exactly {count} MIDDLE-STEP templates in this order:",
        "These are in-flow survey questions — NOT the opening welcome and NOT thank-you closings.",
        "NEVER generate step_role=start or step_role=completion.",
        'NEVER use a "Start survey" quick_reply button — the customer already started from the welcome template.',
    ]
    for idx, slot in enumerate(plan, start=1):
        lines.append(f"  {idx}. step_role={slot['step_role']}")
    return "\n".join(lines) + "\n"


def _survey_questions_system_prompt(
    *,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    template_count: int = DEFAULT_PACK_COUNT,
) -> str:
    count = clamp_pack_count(template_count)
    return (
        "You are an expert WhatsApp Business template copywriter for VoxBulk customer satisfaction surveys. "
        f"Write exactly {count} reusable Meta/Telnyx-compatible MIDDLE-STEP question templates for the WA Survey library. "
        "The welcome/opening message is sent separately from Global System Templates — do NOT generate it again. "
        "British English. Professional, natural, mobile-first. One focused in-flow question per template.\n\n"
        f"{_meta_compliance_rules_block(privacy_mode=privacy_mode)}"
        f"{_library_middle_step_copy_rules_block()}"
        "MANDATORY RULES:\n"
        "• Every template is a survey QUESTION step — never an invite to start a survey.\n"
        "• step_role must be one of the middle roles listed below — never start or completion.\n"
        "• outcome_key must be null on every template.\n"
        "• Do NOT greet (no Hi/Hello/Hey). Do NOT use {{1}} or name variables.\n"
        "• Do NOT say thanks for booking/visiting or welcome the user.\n"
        "• rating / yes_no / helpfulness / abc_choice / feeling_word → quick_reply buttons (max 3).\n"
        "• reason / follow_up / improvement / final_feedback_text → button_type none (free-text reply).\n"
        "• Never label buttons 'Start survey' unless step_role is start (you must not use start).\n\n"
        f"{_reference_copy_rules_block(instruction=instruction, purpose=purpose)}"
        f"{_emoji_rules_block(template_count=count)}"
        f"{_survey_questions_structure_block(template_count=count)}"
        "template_name: unique lowercase snake_case, no voxbulk_survey prefix.\n"
        "category UTILITY. Footer exactly as required for privacy mode."
    )


def _survey_questions_user_prompt(
    *,
    survey_type: SurveyType,
    industry: Industry,
    purpose: str,
    instruction: str,
    privacy_mode: str = PRIVACY_MODE_OFF,
    template_count: int = DEFAULT_PACK_COUNT,
) -> str:
    count = clamp_pack_count(template_count)
    topic = str(survey_type.name or survey_type.slug).strip()
    parts = [
        f"Industry: {industry.name}",
        f"Survey type: {survey_type.name}",
        f"Survey topic: {topic}",
        f"Description: {survey_type.description or survey_type.name}",
        f"Privacy Mode: {'On (anonymous)' if normalize_privacy_mode(privacy_mode) == PRIVACY_MODE_ON else 'Off (identified)'}",
        (
            f"Write {count} distinct MIDDLE-STEP WhatsApp questions about “{topic}” for {industry.name}. "
            "Each template asks one clear question with appropriate quick_reply buttons or free-text reply. "
            "No welcome, no start CTA, no thank-you closing."
        ),
        f"Slot plan: {survey_question_slot_plan(count)}",
    ]
    if purpose.strip():
        parts.append(f"Purpose focus: {purpose.strip()}")
    if instruction.strip():
        parts.append(f"Admin instruction: {instruction.strip()}")
    parts.append(f"Generate exactly {count} templates as JSON.")
    return "\n".join(parts)


def _pack_system_prompt(
    *,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
    company_name: str | None = None,
    template_count: int = PACK_SIZE,
) -> str:
    count = clamp_pack_count(template_count)
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
        f"Write exactly {count} reusable Meta/Telnyx-compatible templates that feel native on WhatsApp — warm, mobile-first, "
        "professional, and visually polished while staying Meta approval-friendly (no spam, no ALL CAPS shouting, "
        "no false urgency). Use British English. Do not use OpenAI Realtime.\n\n"
        f"{_meta_compliance_rules_block(privacy_mode=privacy_mode)}"
        f"{anonymous_block}"
        f"{variable_block}"
        f"{_company_name_prompt_block(company_name=company_name)}"
        f"{style_mix}"
        f"{_reference_copy_rules_block(instruction=instruction, purpose=purpose)}"
        f"{_emoji_rules_block(template_count=count)}"
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
        f"{_pack_structure_block(template_count=count)}"
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
    template_count: int = PACK_SIZE,
) -> str:
    count = clamp_pack_count(template_count)
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
    if count == PACK_SIZE:
        parts.append(
            f"Generate exactly {count} visually attractive, conversational, persuasive WhatsApp templates as JSON. "
            "Include one template per middle step_role, one start, and three completion templates "
            "(outcome_key happy, neutral, unhappy). No duplicate non-completion step_roles."
        )
    else:
        parts.append(
            f"Generate exactly {count} visually attractive, conversational, persuasive WhatsApp templates as JSON "
            f"following this slot plan: {pack_slot_plan(count)}."
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


def _library_template_system_prompt(
    *,
    step_role: str,
    privacy_mode: str = PRIVACY_MODE_OFF,
    instruction: str = "",
    purpose: str = "",
) -> str:
    role = normalize_step_role(step_role)
    if role not in MIDDLE_STEP_ROLES:
        raise SurveyWaTemplatePackError(
            f"Library templates must use a middle step_role ({', '.join(MIDDLE_STEP_ROLES)}), not {role!r}"
        )
    role_rules = {
        "rating": (
            f"rating — quick_reply with exactly 3 text-only scale buttons (max {META_QUICK_REPLY_MAX_BUTTONS}; "
            "e.g. Poor / Okay / Excellent). Body is one short question only — no greeting, no {{variables}}, "
            "no 'reply with a number' or 1–5 scale in prose."
        ),
        "yes_no": "yes_no — quick_reply with exactly 2 text-only buttons (Yes / No). No greeting.",
        "helpfulness": (
            "helpfulness — quick_reply with 3 text-only buttons "
            "(Very helpful / Partly helpful / Not helpful). No greeting."
        ),
        "abc_choice": "abc_choice — quick_reply with 2 or 3 meaningful text-only option buttons. No greeting.",
        "reason": "reason — button_type none; one short why/follow-up question. No greeting or intro.",
        "feeling_word": "feeling_word — quick_reply with 2–3 feeling labels. No greeting.",
        "follow_up": "follow_up — button_type none; short in-flow follow-up. No greeting.",
        "improvement": "improvement — button_type none; ask what could improve. No greeting.",
    }
    return (
        "You are an expert WhatsApp Business template copywriter for VoxBulk customer satisfaction surveys. "
        "Write exactly ONE reusable Meta/Telnyx-compatible MIDDLE-STEP template for the WA Survey template library. "
        "This is NOT the welcome message — that is sent separately. "
        "British English. Professional, natural, mobile-first. "
        "No URLs in body. No reference numbers, promo spam, or misleading claims.\n\n"
        f"{_meta_compliance_rules_block(privacy_mode=privacy_mode)}"
        f"{_library_middle_step_copy_rules_block()}"
        "LIBRARY TEMPLATE RULES (mandatory):\n"
        f"• step_role MUST be exactly “{role}”.\n"
        "• DO NOT generate welcome, thank_you, tell_us_more, start, or completion templates.\n"
        "• DO NOT use outcome_key — set outcome_key to null.\n"
        "• variant_type standard (Privacy Mode Off) unless instruction says anonymous.\n"
        "• category UTILITY.\n"
        "• Copy must be clearly specific to the given industry AND survey type topic.\n"
        "• One focused in-flow question — not a multi-topic survey pack.\n"
        f"• Role behaviour: {role_rules.get(role, role_rules['rating'])}\n\n"
        f"{_reference_copy_rules_block(instruction=instruction, purpose=purpose)}"
        f"{_emoji_rules_block(template_count=1)}"
        "Return JSON with a single `template` object."
    )


def _library_template_user_prompt(
    *,
    survey_type: SurveyType,
    industry: Industry,
    step_role: str,
    purpose: str,
    instruction: str,
) -> str:
    role = normalize_step_role(step_role)
    topic = str(survey_type.name or survey_type.slug).strip()
    parts = [
        f"Industry: {industry.name}",
        f"Industry slug: {industry.slug}",
        f"Survey type: {survey_type.name}",
        f"Survey type slug: {survey_type.slug}",
        f"Survey topic to ask about: {topic}",
        f"Required step_role: {role}",
        f"Description: {survey_type.description or survey_type.name}",
        (
            f"Write one MIDDLE-STEP WhatsApp question about “{topic}” for {industry.name}. "
            "No greeting and no welcome — the customer already received the opening template. "
            "Examples: Hospitality & food + Food quality → “How was the food quality on your visit? ⭐”; "
            "Automotive + Explanation of work → “Was the work explained clearly?” with Yes/No buttons."
        ),
    ]
    if purpose.strip():
        parts.append(f"Purpose focus: {purpose.strip()}")
    if instruction.strip():
        parts.append(f"Admin instruction: {instruction.strip()}")
    parts.append("Return one improved template as JSON.")
    return "\n".join(parts)


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
    apply_company_name_rules: bool = True,
    pack_mode: str = DEFAULT_PACK_MODE,
) -> dict[str, Any]:
    mode = normalize_pack_mode(pack_mode)
    coerced = coerce_meta_template_fields(item, privacy_mode=privacy_mode)
    expected_role = normalize_step_role(
        str(coerced.get("step_role") or coerced.get("purpose") or "")
    )
    if mode == PACK_MODE_SURVEY_QUESTIONS:
        slot_plan = survey_question_slot_plan(max(idx + 1, 1))
        slot_role = normalize_step_role(str(slot_plan[idx]["step_role"])) if idx < len(slot_plan) else expected_role
        coerced = normalize_library_middle_template(coerced, step_role=slot_role or expected_role)
        apply_company_name_rules = False
    normalized, errors = validate_generated_template(
        coerced,
        survey_type=survey_type,
        privacy_mode=privacy_mode,
        instruction=instruction,
        purpose=purpose,
        company_name=company_name,
        apply_company_name_rules=apply_company_name_rules,
    )
    row: dict[str, Any] = {
        "index": idx,
        "raw": item,
        "valid": not errors,
        "errors": errors,
    }
    if not normalized:
        return row
    if mode == PACK_MODE_SURVEY_QUESTIONS:
        lib_errors = validate_library_middle_step_copy(
            body=normalized.get("body") or "",
            header=normalized.get("header") or "",
            step_role=str(normalized.get("step_role") or ""),
        )
        if lib_errors:
            row["valid"] = False
            row["errors"] = errors + lib_errors
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
        template_count: int = DEFAULT_PACK_COUNT,
        industry_id: str | None = None,
        org_id: str | None = None,
        pack_mode: str = DEFAULT_PACK_MODE,
    ) -> dict[str, Any]:
        privacy_mode = normalize_privacy_mode(privacy_mode)
        pack_count = clamp_pack_count(template_count)
        mode = normalize_pack_mode(pack_mode)
        company_name = resolve_wa_survey_company_name(db, org_id=org_id)
        try:
            industry = load_industry_for_prompt(db, survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if industry_id and str(industry_id).strip() != industry.id:
            raise SurveyWaTemplatePackError("Industry does not match survey type")
        if mode == PACK_MODE_SURVEY_QUESTIONS:
            system_prompt = _survey_questions_system_prompt(
                privacy_mode=privacy_mode,
                instruction=instruction,
                purpose=purpose,
                template_count=pack_count,
            )
            user_prompt = _survey_questions_user_prompt(
                survey_type=survey_type,
                industry=industry,
                purpose=purpose,
                instruction=instruction,
                privacy_mode=privacy_mode,
                template_count=pack_count,
            )
            apply_company_rules = False
        else:
            system_prompt = _pack_system_prompt(
                privacy_mode=privacy_mode,
                instruction=instruction,
                purpose=purpose,
                company_name=company_name,
                template_count=pack_count,
            )
            user_prompt = _pack_user_prompt(
                survey_type=survey_type,
                industry=industry,
                purpose=purpose,
                instruction=instruction,
                privacy_mode=privacy_mode,
                company_name=company_name,
                template_count=pack_count,
            )
            apply_company_rules = True
        try:
            raw, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=build_pack_json_schema(pack_count),
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
                apply_company_name_rules=apply_company_rules,
                pack_mode=mode,
            )
            if row.get("valid") and row.get("template"):
                validated.append(row)
            else:
                invalid.append(row)

        composition_errors = _validate_pack_composition(
            [r["template"] for r in validated if r.get("template")],
            template_count=pack_count,
            pack_mode=mode,
        )

        return {
            "ok": True,
            "pack_mode": mode,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "company_name": company_name,
            "survey_type_id": survey_type.id,
            "survey_type_name": survey_type.name,
            "service_type": survey_type.slug,
            "privacy_mode": privacy_mode,
            "theme_variant": str(theme_variant or "").strip() or None,
            "template_count": pack_count,
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
    def generate_library_template(
        db: Session,
        *,
        survey_type: SurveyType,
        step_role: str = "rating",
        purpose: str = "",
        instruction: str = "",
        privacy_mode: str = PRIVACY_MODE_OFF,
        industry_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate one industry+survey-type library template (middle step only, not system templates)."""
        privacy_mode = normalize_privacy_mode(privacy_mode)
        role = normalize_step_role(step_role)
        if role not in MIDDLE_STEP_ROLES:
            raise SurveyWaTemplatePackError(
                f"step_role must be a middle library role ({', '.join(MIDDLE_STEP_ROLES)}), not {role!r}"
            )
        try:
            industry = load_industry_for_prompt(db, survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if survey_type.system_template_kind:
            raise SurveyWaTemplatePackError(
                "Cannot generate library templates for system survey types (welcome/thank_you/tell_us_more)"
            )
        if industry_id and str(industry_id).strip() != industry.id:
            raise SurveyWaTemplatePackError("Industry does not match survey type")
        if getattr(industry, "is_hidden", False):
            raise SurveyWaTemplatePackError("Cannot generate library templates for hidden/system industries")

        purpose = purpose.strip() or str(survey_type.name or "").strip()
        library_instruction = BULK_LIBRARY_MIDDLE_INSTRUCTION
        if instruction.strip():
            library_instruction = f"{library_instruction}\n{instruction.strip()}"

        try:
            raw, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=_library_template_system_prompt(
                    step_role=role,
                    privacy_mode=privacy_mode,
                    instruction=library_instruction,
                    purpose=purpose,
                ),
                user_prompt=_library_template_user_prompt(
                    survey_type=survey_type,
                    industry=industry,
                    step_role=role,
                    purpose=purpose,
                    instruction=library_instruction,
                ),
                json_schema=WA_SINGLE_TEMPLATE_JSON_SCHEMA,
                schema_name="wa_survey_library_template",
                max_output_tokens=4000,
                temperature=0.65,
            )
        except ValueError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        except httpx.TimeoutException as e:
            raise SurveyWaTemplatePackError("OpenAI timed out generating the library template.") from e

        item = raw.get("template")
        if not isinstance(item, dict):
            raise SurveyWaTemplatePackError("OpenAI response missing template object")

        coerced = coerce_meta_template_fields({**item, "step_role": role, "outcome_key": None}, privacy_mode=privacy_mode)
        coerced = normalize_library_middle_template(coerced, step_role=role)
        coerced = attach_auto_followup_to_template_item(
            coerced,
            survey_type=survey_type,
            industry_slug=str(industry.slug or ""),
        )
        middle_errors = validate_library_middle_step_copy(
            body=str(coerced.get("body") or ""),
            header=str(coerced.get("header") or ""),
            step_role=role,
        )
        if middle_errors:
            raise SurveyWaTemplatePackError("; ".join(middle_errors))

        row = _build_pack_item_row(
            db,
            survey_type=survey_type,
            idx=0,
            item=coerced,
            seen_names=set(),
            privacy_mode=privacy_mode,
            instruction=library_instruction,
            purpose=purpose,
            company_name=None,
            apply_company_name_rules=False,
        )
        if not row.get("valid") or not row.get("template"):
            errors = row.get("errors") or ["validation failed"]
            raise SurveyWaTemplatePackError("; ".join(str(e) for e in errors))

        generated_role = normalize_step_role(str(row["template"].get("step_role") or ""))
        if generated_role != role:
            raise SurveyWaTemplatePackError(
                f"OpenAI returned step_role={generated_role!r}, expected {role!r}"
            )
        if generated_role in {"start", "completion"} or str(row["template"].get("outcome_key") or "").strip():
            raise SurveyWaTemplatePackError("Generated template must not be a start/completion/system template")

        return {
            "ok": True,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "survey_type_id": survey_type.id,
            "survey_type_slug": survey_type.slug,
            "survey_type_name": survey_type.name,
            "step_role": role,
            "template": row["template"],
            "openai": meta,
            "privacy_mode": privacy_mode,
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
        pack_mode: str = DEFAULT_PACK_MODE,
    ) -> dict[str, Any]:
        privacy_mode = normalize_privacy_mode(
            privacy_mode or (current_template or {}).get("privacy_mode") or PRIVACY_MODE_OFF
        )
        mode = normalize_pack_mode(pack_mode)
        company_name = resolve_wa_survey_company_name(db, org_id=org_id)
        try:
            industry = load_industry_for_prompt(db, survey_type)
        except SurveyIndustryScopeError as e:
            raise SurveyWaTemplatePackError(str(e)) from e
        if industry_id and str(industry_id).strip() != industry.id:
            raise SurveyWaTemplatePackError("Industry does not match survey type")

        slot_role = normalize_step_role(
            str(
                (current_template or {}).get("step_role")
                or slot_hint
                or survey_question_slot_plan(max(int(index), 0) + 1)[int(index)]["step_role"]
            )
        )
        if mode == PACK_MODE_SURVEY_QUESTIONS:
            library_instruction = BULK_LIBRARY_MIDDLE_INSTRUCTION
            if instruction.strip():
                library_instruction = f"{library_instruction}\n{instruction.strip()}"
            purpose_text = purpose.strip() or str(survey_type.name or "").strip()
            try:
                raw, meta = OpenAIProviderService.responses_json(
                    db,
                    system_prompt=_library_template_system_prompt(
                        step_role=slot_role,
                        privacy_mode=privacy_mode,
                        instruction=library_instruction,
                        purpose=purpose_text,
                    ),
                    user_prompt=_library_template_user_prompt(
                        survey_type=survey_type,
                        industry=industry,
                        step_role=slot_role,
                        purpose=purpose_text,
                        instruction=library_instruction,
                    ),
                    json_schema=WA_SINGLE_TEMPLATE_JSON_SCHEMA,
                    schema_name="wa_survey_library_template",
                    max_output_tokens=4000,
                    temperature=0.72,
                )
            except ValueError as e:
                raise SurveyWaTemplatePackError(str(e)) from e
            item = raw.get("template")
            if not isinstance(item, dict):
                raise SurveyWaTemplatePackError("OpenAI response missing template object")
            item = normalize_library_middle_template(
                {**item, "step_role": slot_role, "outcome_key": None},
                step_role=slot_role,
            )
            apply_company_rules = False
            company_name = None
        else:
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
            apply_company_rules = True

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
            apply_company_name_rules=apply_company_rules,
            pack_mode=mode,
        )
        return {
            "ok": True,
            "item": row,
            "openai": meta,
            "privacy_mode": privacy_mode,
            "company_name": company_name,
            "pack_mode": mode,
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
        if not isinstance(examples, list):
            examples = _extract_example_values(components)
        elif not examples:
            extracted = _extract_example_values(components)
            examples = extracted if extracted else []

        telnyx_name = _ensure_unique_telnyx_name(
            db, _telnyx_pack_name(survey_type.slug, item["template_name"])
        )
        now = _now()
        local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
        privacy_mode = normalize_privacy_mode(item.get("privacy_mode") or privacy_mode)
        variant = privacy_mode_to_variant(privacy_mode)
        outcome_key = str(item.get("outcome_key") or "")[:16] or None
        outcome_vars = item.get("outcome_variables")
        auto_followup = item.get("auto_followup")
        if isinstance(auto_followup, dict):
            outcome_vars = {"auto_followup": auto_followup}
        elif outcome_key and not outcome_vars:
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
            draft_components_json=_dumps(_normalize_draft_components(components)),
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
