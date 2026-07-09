"""Product-scoped WA template names and rows (survey vs customer feedback)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.connection.constants import SERVICE_CUSTOMER_FEEDBACK, SERVICE_SURVEY, normalize_service_code
from app.services.wa_template_cleanup_sync_service import (
    CF_META_PREFIXES,
    SURVEY_META_PREFIXES,
    is_cf_catalog_row,
    is_protected_template,
    is_survey_product_row,
)
from seed_data.wa_survey_template_naming import is_was_survey_name


def _name_lower(name: str | None) -> str:
    return str(name or "").strip().lower()


def is_survey_platform_name(name: str | None) -> bool:
    n = _name_lower(name)
    if not n or is_protected_template_name(n):
        return False
    if is_was_survey_name(n):
        return True
    return n.startswith(SURVEY_META_PREFIXES)


def is_feedback_platform_name(name: str | None) -> bool:
    n = _name_lower(name)
    if not n or is_protected_template_name(n):
        return False
    return n.startswith(CF_META_PREFIXES)


def is_managed_product_remote_name(name: str | None) -> bool:
    """Survey/feedback template names — DB owns identity; Meta pull is status-only."""
    return is_survey_platform_name(name) or is_feedback_platform_name(name)


def is_managed_product_row(db: Session, row: TelnyxWhatsappTemplate) -> bool:
    if is_feedback_platform_name(row.name):
        return True
    return is_survey_platform_row(db, row)


def is_protected_template_name(name: str | None) -> bool:
    from app.services.wa_template_cleanup_sync_service import PROTECTED_PREFIXES

    n = _name_lower(name)
    return any(n.startswith(p) for p in PROTECTED_PREFIXES)


def is_survey_platform_row(db: Session, row: TelnyxWhatsappTemplate) -> bool:
    if is_protected_template(row):
        return False
    if is_was_survey_name(row.name) or is_survey_product_row(row):
        return True
    name = _name_lower(row.name)
    if name.startswith(SURVEY_META_PREFIXES):
        return True
    mapped = db.execute(
        select(SurveyTypeTemplate.id).where(SurveyTypeTemplate.template_id == row.id).limit(1)
    ).scalar_one_or_none()
    return mapped is not None


def is_survey_platform_row_simple(row: TelnyxWhatsappTemplate) -> bool:
    """Fast name-based check when DB join is unnecessary."""
    if is_protected_template(row):
        return False
    return is_survey_platform_name(row.name)


def filter_remote_for_service_code(remote: list[dict], service_code: str | None) -> list[dict]:
    code = normalize_service_code(service_code) or SERVICE_SURVEY
    out: list[dict] = []
    for item in remote or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if code == SERVICE_CUSTOMER_FEEDBACK:
            if is_feedback_platform_name(name):
                out.append(item)
        elif code == SERVICE_SURVEY:
            if is_survey_platform_name(name):
                out.append(item)
        else:
            out.append(item)
    return out


def list_survey_platform_rows(db: Session) -> list[TelnyxWhatsappTemplate]:
    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
    return [row for row in rows if is_survey_platform_row(db, row)]


def count_feedback_local_only(db: Session, *, by_record: dict, by_name_lang: dict) -> int:
    from app.services.customer_feedback.feedback_telnyx_push_service import _feedback_meta_name_for_template
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

    local_only = 0
    for tpl in db.execute(select(FeedbackWaTemplate)).scalars().all():
        try:
            meta_name = _feedback_meta_name_for_template(db, tpl)
        except Exception:
            meta_name = str(tpl.template_key or "").strip()
        if not meta_name:
            local_only += 1
            continue
        fake = TelnyxWhatsappTemplate(name=meta_name, language=str(tpl.language or "en_GB"))
        live = TelnyxWhatsappTemplateSyncService._match_live_item(
            fake, by_record=by_record, by_name_lang=by_name_lang
        )
        if live is None:
            local_only += 1
    return local_only
