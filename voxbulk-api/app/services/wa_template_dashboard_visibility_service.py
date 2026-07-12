"""Hide survey / customer-feedback topics from the user dashboard when WA templates are not ready."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.feedback_telnyx_push_service import (
    english_anchor_template,
    feedback_meta_template_name,
)

_PENDING_STATUSES = frozenset(
    {
        "PENDING",
        "PENDING_APPROVAL",
        "IN_APPEAL",
        "SUBMITTED",
        "DRAFT",
        "LOCAL_DRAFT",
        "UNKNOWN",
    }
)


def is_pending_wa_status(status: str | None) -> bool:
    normalized = str(status or "").strip().upper()
    if not normalized or normalized in _PENDING_STATUSES:
        return True
    if normalized == "APPROVED":
        return False
    if "REJECT" in normalized:
        return False
    return normalized not in {"SYNCED", "LIVE"}


def is_marketing_wa_category(raw: str | None) -> bool:
    return "MARKET" in str(raw or "").strip().upper()


def platform_template_blocks_dashboard(row: TelnyxWhatsappTemplate | None) -> bool:
    if row is None:
        return False
    if is_marketing_wa_category(getattr(row, "category", None)):
        return True
    # Thank-you / tell-us-more / closing / buttonless open text are sent as local session
    # free-form once the customer has replied — Meta APPROVED is not required to list them.
    from app.services.survey_whatsapp_template_service import template_row_must_send_as_session_text

    if template_row_must_send_as_session_text(row):
        return False
    return is_pending_wa_status(getattr(row, "status", None))


def feedback_template_blocks_dashboard(row: FeedbackWaTemplate | None) -> bool:
    if row is None:
        return False
    if is_marketing_wa_template(row):
        return True
    status = str(getattr(row, "telnyx_sync_status", None) or getattr(row, "status", None) or "")
    return is_pending_wa_status(status)


def hidden_platform_survey_type_ids_by_status(db: Session) -> set[str]:
    """Platform WA survey types with any linked template pending or marketing."""
    mappings = list(db.execute(select(SurveyTypeTemplate)).scalars().all())
    if not mappings:
        return set()

    template_ids = {int(m.template_id) for m in mappings if m.template_id is not None}
    templates: dict[int, TelnyxWhatsappTemplate] = {}
    if template_ids:
        for row in db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.id.in_(template_ids))
        ).scalars():
            templates[int(row.id)] = row

    blocked_type_ids: set[str] = set()
    for mapping in mappings:
        survey_type_id = str(mapping.survey_type_id or "").strip()
        if not survey_type_id:
            continue
        tpl = templates.get(int(mapping.template_id or 0))
        if platform_template_blocks_dashboard(tpl):
            blocked_type_ids.add(survey_type_id)
    return blocked_type_ids


def _feedback_meta_name_for_row(db: Session, tpl: FeedbackWaTemplate) -> str:
    industry_slug = ""
    survey_type_slug = ""
    if tpl.industry_id:
        from app.models.customer_feedback import FeedbackIndustry

        industry = db.get(FeedbackIndustry, tpl.industry_id)
        industry_slug = str(getattr(industry, "slug", None) or "")
    if tpl.survey_type_id:
        survey_type = db.get(FeedbackSurveyType, tpl.survey_type_id)
        survey_type_slug = str(getattr(survey_type, "slug", None) or "")
    try:
        anchor = english_anchor_template(db, tpl)
        return feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug,
            survey_type_slug=survey_type_slug,
            name_anchor_id=anchor.id,
        )
    except Exception:  # noqa: BLE001
        return ""


def hidden_feedback_survey_type_ids_by_status(db: Session) -> set[str]:
    """Customer-feedback topics hidden when any step/language or its Meta mirror pair is pending/marketing."""
    rows = list(
        db.execute(
            select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id.is_not(None))
        ).scalars().all()
    )
    if not rows:
        return set()

    platform_by_name: dict[str, TelnyxWhatsappTemplate] = {}
    for row in db.execute(select(TelnyxWhatsappTemplate)).scalars():
        key = str(row.name or "").strip().lower()
        if key:
            platform_by_name[key] = row

    by_type: dict[str, list[FeedbackWaTemplate]] = {}
    for row in rows:
        survey_type_id = str(row.survey_type_id or "").strip()
        if not survey_type_id:
            continue
        by_type.setdefault(survey_type_id, []).append(row)

    hidden: set[str] = set()
    for survey_type_id, templates in by_type.items():
        for tpl in templates:
            if feedback_template_blocks_dashboard(tpl):
                hidden.add(survey_type_id)
                break
            meta_name = _feedback_meta_name_for_row(db, tpl).strip().lower()
            if meta_name:
                mirror = platform_by_name.get(meta_name)
                if platform_template_blocks_dashboard(mirror):
                    hidden.add(survey_type_id)
                    break
    return hidden
