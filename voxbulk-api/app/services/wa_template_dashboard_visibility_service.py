"""Hide survey / customer-feedback topics from the user dashboard when WA templates are not ready."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.feedback_telnyx_push_service import (
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


def _feedback_meta_name_for_row(
    tpl: FeedbackWaTemplate,
    *,
    industry_slug: str = "",
    survey_type_slug: str = "",
) -> str:
    try:
        # name_anchor_id is unused by cfs_* names — skip english_anchor_template (extra DB hit).
        return feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug,
            survey_type_slug=survey_type_slug,
        )
    except Exception:  # noqa: BLE001
        return ""


def hidden_feedback_survey_type_ids_by_status(
    db: Session,
    *,
    survey_type_ids: set[str] | None = None,
) -> set[str]:
    """Customer-feedback topics hidden when any step/language or its Meta mirror pair is pending/marketing."""
    q = select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id.is_not(None))
    if survey_type_ids is not None:
        if not survey_type_ids:
            return set()
        q = q.where(FeedbackWaTemplate.survey_type_id.in_(list(survey_type_ids)))
    rows = list(db.execute(q).scalars().all())
    if not rows:
        return set()

    from app.models.customer_feedback import FeedbackIndustry

    industry_ids = {str(r.industry_id) for r in rows if r.industry_id}
    type_ids = {str(r.survey_type_id) for r in rows if r.survey_type_id}
    industry_slugs: dict[str, str] = {}
    if industry_ids:
        for row in db.execute(select(FeedbackIndustry.id, FeedbackIndustry.slug).where(FeedbackIndustry.id.in_(industry_ids))):
            industry_slugs[str(row.id)] = str(row.slug or "")
    type_slugs: dict[str, str] = {}
    if type_ids:
        for row in db.execute(
            select(FeedbackSurveyType.id, FeedbackSurveyType.slug).where(FeedbackSurveyType.id.in_(type_ids))
        ):
            type_slugs[str(row.id)] = str(row.slug or "")

    meta_by_tpl_id: dict[str, str] = {}
    needed_names: list[str] = []
    for tpl in rows:
        name = _feedback_meta_name_for_row(
            tpl,
            industry_slug=industry_slugs.get(str(tpl.industry_id or ""), ""),
            survey_type_slug=type_slugs.get(str(tpl.survey_type_id or ""), ""),
        ).strip()
        meta_by_tpl_id[str(tpl.id)] = name
        if name:
            needed_names.append(name)

    platform_by_name: dict[str, TelnyxWhatsappTemplate] = {}
    if needed_names:
        unique_lower = list(dict.fromkeys(n.strip().lower() for n in needed_names if n.strip()))
        if unique_lower:
            for row in db.execute(
                select(TelnyxWhatsappTemplate).where(func.lower(TelnyxWhatsappTemplate.name).in_(unique_lower))
            ).scalars():
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
            meta_name = meta_by_tpl_id.get(str(tpl.id), "").strip().lower()
            if meta_name:
                mirror = platform_by_name.get(meta_name)
                if platform_template_blocks_dashboard(mirror):
                    hidden.add(survey_type_id)
                    break
    return hidden
