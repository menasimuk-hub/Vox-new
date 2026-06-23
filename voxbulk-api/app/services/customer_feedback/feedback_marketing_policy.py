"""Platform-wide blocklist for Meta marketing-category WA templates (billing)."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

# When True, marketing opt-in steps and blocked/marketing templates are excluded everywhere.
MARKETING_WA_TEMPLATES_DISABLED = True

_BLOCKLIST_FILE = (
    Path(__file__).resolve().parents[3] / "seed-data" / "wa-templates" / "export-template-names.txt"
)


@lru_cache(maxsize=1)
def blocked_meta_template_names() -> frozenset[str]:
    names: set[str] = set()
    if _BLOCKLIST_FILE.is_file():
        for line in _BLOCKLIST_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip().lower()
            if clean and not clean.startswith("#"):
                names.add(clean)
    return frozenset(names)


def is_blocked_meta_template_name(name: str | None) -> bool:
    clean = str(name or "").strip().lower()
    if not clean:
        return False
    return clean in blocked_meta_template_names()


def marketing_wa_enabled() -> bool:
    return not MARKETING_WA_TEMPLATES_DISABLED


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"true", "1", "yes", "on"}:
            return True
        if clean in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _normalize_category(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_marketing_category(value: str | None) -> bool:
    return _normalize_category(value) == "marketing"


def is_arabic_language(value: str | None) -> bool:
    lang = str(value or "").strip().lower().replace("-", "_")
    return lang == "ar" or lang.startswith("ar_")


def is_marketing_wa_template(row: Any, *, meta_name: str | None = None) -> bool:
    if marketing_wa_enabled():
        return False
    cat = _normalize_category(getattr(row, "meta_category", None) or getattr(row, "category", None))
    key = str(getattr(row, "template_key", None) or "").strip().lower()
    step_role = str(getattr(row, "step_role", None) or "").strip().lower()
    if cat == "marketing" or key == "marketing_opt_in" or step_role == "marketing_opt_in":
        return True
    if meta_name and is_blocked_meta_template_name(meta_name):
        return True
    name = str(getattr(row, "name", None) or "").strip().lower()
    if is_blocked_meta_template_name(name):
        return True
    return False


def is_blocked_telnyx_wa_template(row: Any, *, blocked_names: frozenset[str] | None = None) -> bool:
    """WA Survey rows in telnyx_whatsapp_templates."""
    if marketing_wa_enabled():
        return False
    names = blocked_names if blocked_names is not None else blocked_meta_template_names()
    name = str(getattr(row, "name", None) or "").strip().lower()
    if name in names:
        return True
    return is_marketing_wa_template(row, meta_name=name)


def is_marketing_survey_step(step: dict[str, Any]) -> bool:
    kind = str(step.get("kind") or "").strip().lower()
    key = str(step.get("template_key") or "").strip().lower()
    return kind == "marketing_opt_in" or key == "marketing_opt_in"


def filter_survey_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if marketing_wa_enabled():
        return steps
    return [step for step in steps if not is_marketing_survey_step(step)]


def effective_marketing_opt_in_enabled(flag: bool | None) -> bool:
    if not marketing_wa_enabled():
        return False
    return bool(flag)


def feedback_template_meta_name_for_row(db: Session, tpl: Any) -> str:
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        _feedback_template_meta_context,
        english_anchor_template,
        feedback_meta_template_name,
    )

    industry_slug, survey_slug = _feedback_template_meta_context(db, tpl)
    anchor = english_anchor_template(db, tpl)
    return feedback_meta_template_name(
        tpl,
        industry_slug=industry_slug,
        survey_type_slug=survey_slug,
        name_anchor_id=anchor.id,
    )


def _feedback_template_is_blocklisted(db: Session, row: Any, *, meta_name: str | None = None) -> bool:
    if _feedback_template_block_exempt(db, row):
        return False
    meta = meta_name or feedback_template_meta_name_for_row(db, row)
    return is_marketing_wa_template(row, meta_name=meta)


def _survey_type_wa_block_exempt(db: Session, survey_type_id: str | None) -> bool:
    from app.models.customer_feedback import FeedbackSurveyType

    if not survey_type_id:
        return False
    st = db.get(FeedbackSurveyType, survey_type_id)
    return st is not None and bool(getattr(st, "wa_platform_block_exempt", False))


def _feedback_template_block_exempt(db: Session, row: Any) -> bool:
    return _survey_type_wa_block_exempt(db, getattr(row, "survey_type_id", None))


def _survey_type_admin_reenabled(db: Session, survey_type_id: str | None) -> bool:
    """When admin enabled a blocklisted type, keep it active across restarts."""
    return _survey_type_wa_block_exempt(db, survey_type_id)


def _collect_blocked_feedback_template_ids(db: Session) -> set[str]:
    from app.models.customer_feedback import FeedbackWaTemplate

    rows = list(db.execute(select(FeedbackWaTemplate)).scalars().all())
    meta_by_id: dict[str, str] = {}
    for row in rows:
        meta_by_id[str(row.id)] = feedback_template_meta_name_for_row(db, row)

    blocked_ids: set[str] = set()
    blocked_meta_names: set[str] = set()
    blocked_type_keys: set[tuple[str, str]] = set()

    for row in rows:
        meta = meta_by_id[str(row.id)]
        if not _feedback_template_is_blocklisted(db, row, meta_name=meta):
            continue
        if _survey_type_admin_reenabled(db, row.survey_type_id):
            continue
        blocked_ids.add(str(row.id))
        blocked_meta_names.add(meta)
        if row.survey_type_id and row.template_key:
            blocked_type_keys.add((str(row.survey_type_id), str(row.template_key)))

    for row in rows:
        rid = str(row.id)
        if rid in blocked_ids:
            continue
        if _survey_type_admin_reenabled(db, row.survey_type_id):
            continue
        meta = meta_by_id[rid]
        if meta in blocked_meta_names:
            blocked_ids.add(rid)
            continue
        key = (str(row.survey_type_id or ""), str(row.template_key or ""))
        if key[0] and key in blocked_type_keys:
            blocked_ids.add(rid)

    return blocked_ids


def _collect_blocked_telnyx_template_ids(db: Session) -> set[int]:
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
    names = blocked_meta_template_names()
    blocked_ids: set[int] = set()
    blocked_names: set[str] = set()

    for row in rows:
        if is_blocked_telnyx_wa_template(row, blocked_names=names):
            blocked_ids.add(int(row.id))
            blocked_names.add(str(row.name or "").strip().lower())

    changed = True
    while changed:
        changed = False
        for row in rows:
            rid = int(row.id)
            if rid in blocked_ids:
                continue
            name = str(row.name or "").strip().lower()
            parent_id = getattr(row, "parent_template_id", None)
            if name in blocked_names or (parent_id is not None and int(parent_id) in blocked_ids):
                blocked_ids.add(rid)
                if name:
                    blocked_names.add(name)
                changed = True

    return blocked_ids


def apply_platform_wa_marketing_blocks(db: Session) -> dict[str, int]:
    """Deactivate blocklisted feedback + survey templates (safe on every startup)."""
    from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    feedback_deactivated = 0
    survey_deactivated = 0
    survey_types_deactivated = 0
    now = datetime.utcnow()

    blocked_feedback_ids = _collect_blocked_feedback_template_ids(db)
    for row in db.execute(select(FeedbackWaTemplate)).scalars():
        if str(row.id) not in blocked_feedback_ids:
            continue
        if row.is_active:
            row.is_active = False
            feedback_deactivated += 1
        if not is_marketing_category(row.meta_category):
            row.meta_category = "marketing"
        row.updated_at = now
        db.add(row)

    blocked_type_ids: set[str] = set()
    for row in db.execute(select(FeedbackWaTemplate)).scalars():
        if str(row.id) in blocked_feedback_ids and row.survey_type_id:
            blocked_type_ids.add(str(row.survey_type_id))

    for type_id in blocked_type_ids:
        if _survey_type_admin_reenabled(db, type_id):
            continue
        st = db.get(FeedbackSurveyType, type_id)
        if st is None:
            continue
        changed = False
        if st.is_active:
            st.is_active = False
            survey_types_deactivated += 1
            changed = True
        if not bool(getattr(st, "customer_hidden", False)):
            st.customer_hidden = True
            changed = True
        if changed:
            st.updated_at = now
            db.add(st)

    blocked_telnyx_ids = _collect_blocked_telnyx_template_ids(db)
    for row in db.execute(select(TelnyxWhatsappTemplate)).scalars():
        if int(row.id) not in blocked_telnyx_ids:
            continue
        if row.active_for_survey:
            row.active_for_survey = False
            survey_deactivated += 1
        row.updated_at = now
        db.add(row)

    if feedback_deactivated or survey_deactivated or survey_types_deactivated:
        db.commit()

    return {
        "feedback_deactivated": feedback_deactivated,
        "survey_deactivated": survey_deactivated,
        "survey_types_deactivated": survey_types_deactivated,
        "blocklist_size": len(blocked_meta_template_names()),
    }


def repair_customer_hidden_flags(db: Session) -> dict[str, int]:
    """Ensure disabled survey types stay hidden from the customer catalog."""
    from app.models.customer_feedback import FeedbackSurveyType

    repaired = 0
    now = datetime.utcnow()
    for st in db.execute(select(FeedbackSurveyType)).scalars():
        should_hide = not bool(st.is_active)
        if not should_hide and not _survey_type_admin_reenabled(db, st.id):
            if not survey_type_has_sendable_template(db, st.id):
                should_hide = True
        current_hidden = bool(getattr(st, "customer_hidden", False))
        if should_hide == current_hidden:
            continue
        st.customer_hidden = should_hide
        if should_hide and st.is_active:
            st.is_active = False
        st.updated_at = now
        db.add(st)
        repaired += 1
    if repaired:
        db.commit()
    return {"repaired": repaired}


def set_feedback_survey_type_active(db: Session, survey_type_id: str, *, active: bool) -> dict[str, Any]:
    """Admin toggle — enable/disable survey type and all its WA templates (EN + AR pairs)."""
    from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate

    row = db.get(FeedbackSurveyType, survey_type_id)
    if row is None:
        raise ValueError("Survey type not found")
    now = datetime.utcnow()
    row.is_active = bool(active)
    row.wa_platform_block_exempt = bool(active)
    row.customer_hidden = not bool(active)
    row.updated_at = now
    db.add(row)

    tpl_rows = list(
        db.execute(select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == survey_type_id)).scalars().all()
    )
    for tpl in tpl_rows:
        tpl.is_active = bool(active)
        tpl.updated_at = now
        db.add(tpl)

    db.commit()
    db.refresh(row)
    locations_updated = 0
    if not active:
        from app.services.customer_feedback.location_service import FeedbackLocationService

        locations_updated = FeedbackLocationService.purge_survey_type_from_locations(db, survey_type_id)
    return {
        "id": row.id,
        "is_active": row.is_active,
        "customer_hidden": bool(getattr(row, "customer_hidden", False)),
        "templates_updated": len(tpl_rows),
        "locations_updated": locations_updated,
    }


def survey_type_has_sendable_template(db: Session, survey_type_id: str) -> bool:
    from app.models.customer_feedback import FeedbackWaTemplate
    from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES

    tpl_rows = list(
        db.execute(
            select(FeedbackWaTemplate).where(
                FeedbackWaTemplate.survey_type_id == survey_type_id,
                FeedbackWaTemplate.is_active.is_(True),
            )
        ).scalars().all()
    )
    for tpl in tpl_rows:
        if not _feedback_template_is_blocklisted(db, tpl):
            lang = str(tpl.language or "").strip()
            if lang in ENGLISH_TEMPLATE_LANGUAGES or lang.lower().startswith("en"):
                return True
    return False


def assert_whatsapp_template_send_allowed(*, template_name: str | None) -> str | None:
    if marketing_wa_enabled():
        return None
    if is_blocked_meta_template_name(template_name):
        return f"WhatsApp template '{template_name}' is blocked (Meta marketing category)."
    return None
