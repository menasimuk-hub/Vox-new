"""WA Survey step bank — select 4–6 pages from a 10-template OpenAI pack."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_industry_scope import template_matches_survey_industry
from app.services.survey_type_template_service import (
    SurveyTypeTemplateService,
    template_belongs_to_survey_type,
)
from app.services.survey_whatsapp_template_service import (
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    SurveyWhatsappTemplateService,
    _buttons_from_components,
    _effective_components,
)
from app.services.wa_template_privacy import (
    normalize_privacy_mode,
    resolve_mapping_privacy_mode,
    resolve_row_privacy_mode,
    variant_to_privacy_mode,
)

REQUIRED_STEP_ROLES = frozenset({"start", "completion"})
MIDDLE_STEP_ROLES: tuple[str, ...] = (
    "rating",
    "yes_no",
    "helpfulness",
    "abc_choice",
    "reason",
    "feeling_word",
    "follow_up",
    "improvement",
)
ALL_STEP_ROLES = REQUIRED_STEP_ROLES | set(MIDDLE_STEP_ROLES)
PACK_STEP_ROLES: tuple[str, ...] = (
    "start",
    "rating",
    "yes_no",
    "helpfulness",
    "abc_choice",
    "reason",
    "feeling_word",
    "follow_up",
    "improvement",
    "completion",
)
AUTO_MIDDLE_PRIORITY: tuple[str, ...] = MIDDLE_STEP_ROLES
MIN_SURVEY_PAGES = 4
MAX_SURVEY_PAGES = 6

STEP_REPLY_CONFIG: dict[str, dict[str, Any]] = {
    "rating": {
        "reply_type": "choice",
        "options": [str(i) for i in range(11)],
    },
    "yes_no": {"reply_type": "choice", "options": ["Yes", "No"]},
    "helpfulness": {
        "reply_type": "choice",
        "options": ["Very helpful", "Somewhat helpful", "Not helpful"],
    },
    "abc_choice": {
        "reply_type": "choice",
        "options": ["Option A", "Option B", "Option C"],
    },
    "reason": {"reply_type": "long_text", "options": []},
    "feeling_word": {
        "reply_type": "choice",
        "options": ["Great", "Okay", "Disappointing", "Frustrating"],
    },
    "follow_up": {"reply_type": "text", "options": []},
    "improvement": {"reply_type": "long_text", "options": []},
}


def normalize_step_role(raw: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")
    aliases = {
        "intro": "start",
        "opening": "start",
        "start_survey": "start",
        "close": "completion",
        "closing": "completion",
        "thank_you": "completion",
        "nps": "rating",
        "score": "rating",
        "yesno": "yes_no",
        "abc": "abc_choice",
        "multiple_choice": "abc_choice",
        "followup": "follow_up",
    }
    return aliases.get(key, key)


def page_count_from_length(length: str | int | None, *, default: int = 5) -> int:
    if isinstance(length, int):
        return max(MIN_SURVEY_PAGES, min(MAX_SURVEY_PAGES, length))
    key = str(length or "").strip().lower()
    mapping = {"short": 4, "standard": 5, "detailed": 6, "4": 4, "5": 5, "6": 6}
    if key in mapping:
        return mapping[key]
    try:
        return max(MIN_SURVEY_PAGES, min(MAX_SURVEY_PAGES, int(key)))
    except (TypeError, ValueError):
        return default


def _body_text(row: TelnyxWhatsappTemplate) -> str:
    components = _effective_components(row)
    for comp in components:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
            return str(comp.get("text") or "").strip()
    return str(row.body_preview or "").strip()


def _footer_text(row: TelnyxWhatsappTemplate) -> str:
    components = _effective_components(row)
    for comp in components:
        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "FOOTER":
            return str(comp.get("text") or "").strip()
    return ""


def _mapping_score(
    item: dict[str, Any],
    mapping: Any,
    *,
    variant_key: str,
) -> int:
    score = 0
    if str(item.get("approval_status") or "").upper() == "APPROVED":
        score += 10
    if variant_key == VARIANT_ANONYMOUS and getattr(mapping, "is_default_anonymous", False):
        score += 5
    if variant_key == VARIANT_STANDARD and getattr(mapping, "is_default_standard", False):
        score += 5
    return score


def step_bank_item_from_template(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    components = _effective_components(row)
    role = normalize_step_role(row.step_role or "")
    return {
        "template_id": row.id,
        "step_role": role,
        "template_name": row.name,
        "display_name": row.display_name or row.name,
        "title": row.display_name or row.name,
        "body": _body_text(row),
        "footer": _footer_text(row),
        "variant_type": row.variant_type or VARIANT_STANDARD,
        "approval_status": str(row.status or "UNKNOWN").upper(),
        "status": str(row.status or "UNKNOWN").upper(),
        "buttons": _buttons_from_components(components),
        "reply_type": STEP_REPLY_CONFIG.get(role, {}).get("reply_type", "text"),
        "options": STEP_REPLY_CONFIG.get(role, {}).get("options", []),
    }


def load_step_bank(
    db: Session,
    *,
    survey_type_id: str,
    variant: str = VARIANT_STANDARD,
    privacy_mode: str | None = None,
) -> dict[str, Any]:
    variant_key = str(variant or VARIANT_STANDARD).strip().lower()
    target_privacy = normalize_privacy_mode(privacy_mode) if privacy_mode else variant_to_privacy_mode(variant_key)
    survey_type = db.get(SurveyType, survey_type_id)
    mappings = SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)
    by_role: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []

    for mapping in mappings:
        row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
        if row is None or not row.active_for_survey:
            continue
        if survey_type is not None and not template_belongs_to_survey_type(row, survey_type):
            if not (mapping.is_default_standard or mapping.is_default_anonymous):
                continue
        if survey_type is not None and not template_matches_survey_industry(row, survey_type, mapping=mapping):
            continue
        row_pm = resolve_row_privacy_mode(row)
        map_pm = resolve_mapping_privacy_mode(mapping, template_row=row)
        if row_pm != target_privacy or map_pm != target_privacy:
            continue
        row_variant = str(row.variant_type or VARIANT_STANDARD).strip().lower()
        expected_variant = VARIANT_ANONYMOUS if target_privacy == "on" else VARIANT_STANDARD
        if row_variant != expected_variant:
            continue
        role = normalize_step_role(row.step_role or "")
        if not role or role not in ALL_STEP_ROLES:
            continue
        item = step_bank_item_from_template(row)
        item["privacy_mode"] = row_pm
        item["mapping"] = {
            "usable_as_standard": bool(mapping.usable_as_standard),
            "usable_as_anonymous": bool(mapping.usable_as_anonymous),
            "is_default_standard": bool(mapping.is_default_standard),
            "is_default_anonymous": bool(mapping.is_default_anonymous),
        }
        item["_mapping"] = mapping
        items.append(item)
        existing = by_role.get(role)
        if existing is None:
            by_role[role] = item
            continue
        existing_score = _mapping_score(existing, existing.get("_mapping"), variant_key=variant_key)
        new_score = _mapping_score(item, mapping, variant_key=variant_key)
        if new_score > existing_score:
            by_role[role] = item

    for role, item in by_role.items():
        item.pop("_mapping", None)

    suggestions: dict[str, list[str]] = {}
    for count in (4, 5, 6):
        try:
            suggestions[str(count)] = build_page_roles(
                page_count=count,
                bank_by_role=by_role,
                auto_select=True,
            )
        except ValueError:
            suggestions[str(count)] = []

    return {
        "items": items,
        "by_role": by_role,
        "available_roles": sorted(by_role.keys()),
        "missing_roles": [r for r in PACK_STEP_ROLES if r not in by_role],
        "middle_roles": [r for r in MIDDLE_STEP_ROLES if r in by_role],
        "suggested_page_roles": suggestions,
        "privacy_mode": target_privacy,
        "variant": variant_key,
    }


def auto_select_middle_roles(page_count: int, bank: dict[str, dict[str, Any]]) -> list[str]:
    need = max(0, page_count - 2)
    selected: list[str] = []
    for role in AUTO_MIDDLE_PRIORITY:
        if role in bank and role not in selected:
            selected.append(role)
        if len(selected) >= need:
            break
    return selected


def build_page_roles(
    *,
    page_count: int,
    bank_by_role: dict[str, dict[str, Any]],
    selected_middle: list[str] | None = None,
    auto_select: bool = True,
) -> list[str]:
    count = max(MIN_SURVEY_PAGES, min(MAX_SURVEY_PAGES, int(page_count)))
    if "start" not in bank_by_role or "completion" not in bank_by_role:
        raise ValueError("Step bank must include start and completion templates")
    middle = list(selected_middle or [])
    if auto_select or not middle:
        middle = auto_select_middle_roles(count, bank_by_role)
    need = count - 2
    if len(middle) < need:
        raise ValueError(f"Not enough middle steps in bank — need {need}, have {len(middle)}")
    middle = middle[:need]
    return ["start", *middle, "completion"]


def validate_survey_pages(page_roles: list[str], *, page_count: int | None = None) -> list[str]:
    errors: list[str] = []
    expected = page_count or len(page_roles)
    if expected < MIN_SURVEY_PAGES or expected > MAX_SURVEY_PAGES:
        errors.append(f"Survey must be {MIN_SURVEY_PAGES}–{MAX_SURVEY_PAGES} pages")
    if len(page_roles) != expected:
        errors.append(f"Expected {expected} pages, got {len(page_roles)}")
    if not page_roles:
        return errors
    if page_roles[0] != "start":
        errors.append("First page must be start")
    if page_roles[-1] != "completion":
        errors.append("Last page must be completion")
    middle = page_roles[1:-1]
    if len(set(middle)) != len(middle):
        errors.append("Duplicate middle step roles are not allowed")
    for role in page_roles:
        if role not in ALL_STEP_ROLES:
            errors.append(f"Unknown step role: {role}")
    return errors


def question_from_step(item: dict[str, Any]) -> dict[str, Any]:
    role = str(item.get("step_role") or "")
    cfg = STEP_REPLY_CONFIG.get(role, {})
    text = str(item.get("body") or item.get("title") or role.replace("_", " ").title()).strip()
    return {
        "step_role": role,
        "template_id": item.get("template_id"),
        "text": text,
        "reply_type": cfg.get("reply_type", "text"),
        "options": list(cfg.get("options") or []),
    }


def build_survey_pages(
    page_roles: list[str],
    bank_by_role: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for idx, role in enumerate(page_roles, start=1):
        item = bank_by_role.get(role)
        if not item:
            raise ValueError(f"Missing step bank template for role: {role}")
        page = {
            "page": idx,
            "step_role": role,
            "template_id": item.get("template_id"),
            "title": item.get("title") or role,
            "body": item.get("body") or "",
            "footer": item.get("footer") or "",
        }
        if role in MIDDLE_STEP_ROLES:
            page["question"] = question_from_step(item)
        pages.append(page)
    return pages


def build_flow_steps_from_pages(pages: list[dict[str, Any]], *, variant: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for page in pages:
        role = page["step_role"]
        if role == "start":
            steps.append(
                {
                    "step": len(steps) + 1,
                    "kind": "template_outbound",
                    "step_role": "start",
                    "title": page.get("title") or "Start",
                    "body": page.get("body") or "",
                    "description": "WhatsApp template intro message.",
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "kind": "user_action",
                    "step_role": "start",
                    "title": "Recipient taps to begin",
                    "description": "Simulated button tap opens the survey session.",
                }
            )
        elif role == "completion":
            steps.append(
                {
                    "step": len(steps) + 1,
                    "kind": "closing",
                    "step_role": "completion",
                    "title": page.get("title") or "Thank you",
                    "body": page.get("body") or "",
                    "description": "Closing message.",
                }
            )
        else:
            q = page.get("question") or {}
            steps.append(
                {
                    "step": len(steps) + 1,
                    "kind": "survey_question",
                    "step_role": role,
                    "title": page.get("title") or role.replace("_", " ").title(),
                    "body": q.get("text") or page.get("body") or "",
                    "description": f"Survey step: {role}",
                }
            )
    if variant == VARIANT_ANONYMOUS:
        for step in steps:
            step["anonymous"] = True
    return steps


def resolve_start_template(db: Session, bank_by_role: dict[str, dict[str, Any]]) -> TelnyxWhatsappTemplate | None:
    start = bank_by_role.get("start")
    if not start or not start.get("template_id"):
        return None
    return db.get(TelnyxWhatsappTemplate, int(start["template_id"]))


class SurveyStepBankService:
    @staticmethod
    def get_bank(
        db: Session,
        *,
        survey_type: SurveyType,
        variant: str = VARIANT_STANDARD,
        privacy_mode: str | None = None,
    ) -> dict[str, Any]:
        bank = load_step_bank(
            db,
            survey_type_id=survey_type.id,
            variant=variant,
            privacy_mode=privacy_mode,
        )
        return {
            "ok": True,
            "industry_id": survey_type.industry_id,
            "survey_type_id": survey_type.id,
            "variant": variant,
            "privacy_mode": bank.get("privacy_mode") or variant_to_privacy_mode(variant),
            "pack_size": len(PACK_STEP_ROLES),
            **bank,
        }

    @staticmethod
    def compose_survey(
        db: Session,
        *,
        survey_type: SurveyType,
        variant: str = VARIANT_STANDARD,
        privacy_mode: str | None = None,
        page_count: int = 5,
        auto_select: bool = True,
        selected_step_roles: list[str] | None = None,
    ) -> dict[str, Any]:
        bank = load_step_bank(
            db,
            survey_type_id=survey_type.id,
            variant=variant,
            privacy_mode=privacy_mode,
        )
        by_role = bank["by_role"]
        if selected_step_roles:
            roles = [normalize_step_role(r) for r in selected_step_roles]
            errors = validate_survey_pages(roles, page_count=page_count)
            if errors:
                raise ValueError("; ".join(errors))
        else:
            roles = build_page_roles(
                page_count=page_count,
                bank_by_role=by_role,
                auto_select=auto_select,
            )
        pages = build_survey_pages(roles, by_role)
        start_row = resolve_start_template(db, by_role)
        completion_body = by_role.get("completion", {}).get("body") or "Thank you — your feedback helps us improve."
        middle_questions = [p["question"] for p in pages if p.get("question")]
        intro_body = by_role.get("start", {}).get("body") or ""

        preview = {}
        if start_row is not None:
            preview = SurveyWhatsappTemplateService.build_preview(db, start_row)

        return {
            "page_count": page_count,
            "page_roles": roles,
            "pages": pages,
            "questions": [q["text"] for q in middle_questions],
            "whatsapp_flow": {
                "intro": preview.get("rendered_body") or intro_body,
                "questions": middle_questions,
                "closing": completion_body,
                "page_roles": roles,
            },
            "start_template_id": start_row.id if start_row else None,
            "completion_body": completion_body,
            "flow_steps": build_flow_steps_from_pages(pages, variant=variant),
            "template_preview": preview,
            "step_bank_available": bank["available_roles"],
            "step_bank_missing": bank["missing_roles"],
        }
