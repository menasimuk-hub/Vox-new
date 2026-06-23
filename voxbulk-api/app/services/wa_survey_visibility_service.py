"""Customer visibility for main WA Survey types (survey_types table)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_service import SurveyTypeService, survey_type_to_dict
from app.services.survey_type_template_service import SurveyTypeTemplateService


def _wa_survey_type_block_exempt(db: Session, survey_type_id: str | None) -> bool:
    if not survey_type_id:
        return False
    st = db.get(SurveyType, survey_type_id)
    return st is not None and bool(getattr(st, "wa_platform_block_exempt", False))


def wa_survey_type_has_sendable_template(db: Session, survey_type_id: str) -> bool:
    from app.services.customer_feedback.feedback_marketing_policy import is_blocked_telnyx_wa_template

    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
            .where(
                SurveyTypeTemplate.survey_type_id == survey_type_id,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
        ).scalars().all()
    )
    for tpl in rows:
        if not is_blocked_telnyx_wa_template(tpl):
            return True
    return False


def is_wa_survey_type_customer_selectable(
    db: Session,
    survey_type_id: str,
    *,
    industry_id: str | None = None,
) -> bool:
    row = db.get(SurveyType, survey_type_id)
    if row is None or row.system_template_kind:
        return False
    if not bool(row.is_active) or bool(getattr(row, "customer_hidden", False)):
        return False
    if industry_id and str(row.industry_id) != str(industry_id):
        return False
    return wa_survey_type_has_sendable_template(db, survey_type_id)


def list_wa_survey_customer_catalog_types(
    db: Session,
    *,
    industry_id: str | None = None,
) -> list[dict[str, Any]]:
    q = (
        select(SurveyType)
        .where(
            SurveyType.is_active.is_(True),
            SurveyType.customer_hidden.is_(False),
            SurveyType.system_template_kind.is_(None),
        )
        .order_by(SurveyType.sort_order, SurveyType.name)
    )
    if industry_id:
        q = q.where(SurveyType.industry_id == industry_id)
    rows = list(db.execute(q).scalars().all())
    items: list[dict[str, Any]] = []
    for row in rows:
        item = survey_type_to_dict(row)
        item["customer_selectable"] = True
        item["customer_hidden"] = bool(getattr(row, "customer_hidden", False))
        items.append(item)
    return items


def set_wa_survey_type_active(db: Session, survey_type_id: str, *, active: bool) -> dict[str, Any]:
    from app.services.customer_feedback.feedback_marketing_policy import is_blocked_telnyx_wa_template

    row = db.get(SurveyType, survey_type_id)
    if row is None:
        raise ValueError("Survey type not found")
    if row.system_template_kind:
        raise ValueError("System template types cannot be enabled or disabled")

    now = datetime.utcnow()
    row.is_active = bool(active)
    row.wa_platform_block_exempt = bool(active)
    row.customer_hidden = not bool(active)
    row.updated_at = now
    db.add(row)

    tpl_rows: list[TelnyxWhatsappTemplate] = []
    seen: set[int] = set()
    for template_id in SurveyTypeService._linked_template_ids(db, survey_type_id):
        tpl = db.get(TelnyxWhatsappTemplate, template_id)
        if tpl is not None:
            tpl_rows.append(tpl)
            seen.add(int(tpl.id))
    for tpl in db.execute(
        select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.survey_type_id == survey_type_id)
    ).scalars():
        if int(tpl.id) not in seen:
            tpl_rows.append(tpl)
    for tpl in tpl_rows:
        if active and is_blocked_telnyx_wa_template(tpl):
            continue
        tpl.active_for_survey = bool(active)
        tpl.updated_at = now
        db.add(tpl)

    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "is_active": row.is_active,
        "customer_hidden": bool(getattr(row, "customer_hidden", False)),
        "templates_updated": len(tpl_rows),
    }


def repair_wa_survey_customer_hidden_flags(db: Session) -> dict[str, int]:
    repaired = 0
    now = datetime.utcnow()
    for st in db.execute(select(SurveyType)).scalars():
        if st.system_template_kind:
            continue
        should_hide = not bool(st.is_active)
        current_hidden = bool(getattr(st, "customer_hidden", False))
        if should_hide == current_hidden:
            continue
        st.customer_hidden = should_hide
        st.updated_at = now
        db.add(st)
        repaired += 1
    if repaired:
        db.commit()
    return {"repaired": repaired}


def sync_wa_survey_type_customer_visibility(db: Session, survey_type_id: str | None) -> bool:
    """When no sendable templates remain, hide the survey type from the customer catalog."""
    clean_id = str(survey_type_id or "").strip()
    if not clean_id:
        return False
    row = db.get(SurveyType, clean_id)
    if row is None or row.system_template_kind:
        return False
    now = datetime.utcnow()
    selectable = is_wa_survey_type_customer_selectable(db, clean_id, industry_id=row.industry_id)
    if selectable:
        if bool(getattr(row, "customer_hidden", False)) and bool(row.is_active):
            row.customer_hidden = False
            row.updated_at = now
            db.add(row)
            db.commit()
        return False
    if not bool(row.is_active):
        return False
    row.customer_hidden = True
    row.updated_at = now
    db.add(row)
    db.commit()
    return True
