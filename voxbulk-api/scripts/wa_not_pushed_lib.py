"""Shared helpers for list/diagnose/fix WA survey templates not on Meta (buttoned only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SYNC_DRAFT,
    SYNC_ERROR,
    SYNC_LOCAL_CHANGES,
    _buttons_from_components,
    _effective_components,
    _has_remote_telnyx_id,
    telnyx_sync_ui_label,
    template_row_has_buttons,
)
from app.services.wa_template_cleanup_sync_service import is_protected_template

_ON_META_STATUSES = frozenset({"APPROVED", "PENDING"})


def is_on_meta_live(row: TelnyxWhatsappTemplate) -> bool:
    """True when Meta shows APPROVED/PENDING and we have a real remote template id."""
    remote_status = str(row.status or "").upper()
    if remote_status not in _ON_META_STATUSES:
        return False
    record_id = str(row.telnyx_record_id or "").strip()
    if not record_id or record_id.startswith("local-"):
        return False
    if record_id.startswith("local_test_"):
        return False
    return _has_remote_telnyx_id(row)


def is_not_on_meta(row: TelnyxWhatsappTemplate) -> bool:
    """True when template is not live on Meta (not APPROVED/PENDING with remote id)."""
    return not is_on_meta_live(row)


def needs_meta_push(row: TelnyxWhatsappTemplate) -> bool:
    """True when a push/sync to Meta is still required (includes live-but-out-of-sync)."""
    if is_not_on_meta(row):
        return True
    if str(row.last_push_error or "").strip():
        return True
    sync_status = str(row.local_sync_status or "").strip().lower()
    if sync_status in {SYNC_DRAFT, SYNC_LOCAL_CHANGES, SYNC_ERROR}:
        return True
    label = telnyx_sync_ui_label(row).lower()
    return "not synced" in label or "sync failed" in label or "out of sync" in label


def button_count(row: TelnyxWhatsappTemplate) -> int:
    return len(_buttons_from_components(_effective_components(row)))


def record_id_label(row: TelnyxWhatsappTemplate) -> str:
    rid = str(row.telnyx_record_id or "").strip()
    if not rid:
        return "missing"
    if rid.startswith("local-"):
        return "local-id"
    if rid.startswith("local_test_"):
        return "test-id"
    if rid.startswith("meta-"):
        return "meta-id"
    return "remote-id"


def is_out_of_sync_on_meta(row: TelnyxWhatsappTemplate) -> bool:
    return is_on_meta_live(row) and needs_meta_push(row)


def is_stale_approved_local(row: TelnyxWhatsappTemplate) -> bool:
    """APPROVED in DB but no real Meta record id — status is stale; needs push."""
    return str(row.status or "").upper() == "APPROVED" and not is_on_meta_live(row)


def iter_survey_keeper_rows(
    db: Session,
    *,
    industry_slug: str | None = None,
    name_like: str | None = None,
) -> list[TelnyxWhatsappTemplate]:
    """Survey templates linked via mapping or survey_type_id; excludes protected interview/sales."""
    mapped_ids = {
        int(tid)
        for tid in db.execute(select(SurveyTypeTemplate.template_id)).scalars().all()
        if tid is not None
    }

    stmt = select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name)
    if name_like:
        stmt = stmt.where(TelnyxWhatsappTemplate.name.ilike(f"%{name_like.strip()}%"))

    industry_type_ids: set[str] | None = None
    if industry_slug:
        slug = industry_slug.strip().lower()
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            raise ValueError(f"Industry not found for slug={slug!r}")
        industry_type_ids = {
            str(tid)
            for tid in db.scalars(select(SurveyType.id).where(SurveyType.industry_id == industry.id)).all()
        }

    rows_by_id: dict[int, TelnyxWhatsappTemplate] = {}
    for row in db.execute(stmt).scalars().all():
        if is_protected_template(row):
            continue
        st_id = str(row.survey_type_id or "").strip()
        in_mapping = int(row.id) in mapped_ids
        if not in_mapping and not st_id:
            continue
        if industry_type_ids is not None and st_id and st_id not in industry_type_ids:
            if not in_mapping:
                continue
            mapped_st_ids = {
                str(m.survey_type_id)
                for m in db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.template_id == row.id)
                ).scalars().all()
            }
            if not mapped_st_ids.intersection(industry_type_ids):
                continue
        rows_by_id[int(row.id)] = row

    return list(rows_by_id.values())


def split_buttoned_buttonless(rows: list[TelnyxWhatsappTemplate]) -> tuple[list[TelnyxWhatsappTemplate], list[TelnyxWhatsappTemplate]]:
    buttoned: list[TelnyxWhatsappTemplate] = []
    buttonless: list[TelnyxWhatsappTemplate] = []
    for row in rows:
        if template_row_has_buttons(row):
            buttoned.append(row)
        else:
            buttonless.append(row)
    return buttoned, buttonless


def industry_slug_for_row(db: Session, row: TelnyxWhatsappTemplate) -> str | None:
    st_id = str(row.survey_type_id or "").strip()
    if st_id:
        st = db.get(SurveyType, st_id)
        if st and st.industry_id:
            ind = db.get(Industry, st.industry_id)
            if ind:
                return str(ind.slug or "") or None
    mapping = db.execute(
        select(SurveyTypeTemplate)
        .where(SurveyTypeTemplate.template_id == row.id)
        .limit(1)
    ).scalar_one_or_none()
    if mapping and mapping.industry_id:
        ind = db.get(Industry, mapping.industry_id)
        if ind:
            return str(ind.slug or "") or None
    return None


def row_summary(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "telnyx_record_id": row.telnyx_record_id,
        "record_id_kind": record_id_label(row),
        "on_meta_live": is_on_meta_live(row),
        "stale_approved_local": is_stale_approved_local(row),
        "local_sync_status": row.local_sync_status,
        "sync_label": telnyx_sync_ui_label(row),
        "button_count": button_count(row),
        "last_push_error": (row.last_push_error or "")[:300] or None,
        "industry_slug": industry_slug_for_row(db, row),
    }
