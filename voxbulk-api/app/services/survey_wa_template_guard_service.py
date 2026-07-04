"""Guards for WA survey template sync — system kinds, utility rewrite, content mutation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS

_SYSTEM_STEP_ROLES = frozenset(SYSTEM_TEMPLATE_KINDS)


def survey_type_system_kind(db: Session, row: TelnyxWhatsappTemplate) -> str | None:
    kind = str(getattr(row, "step_role", None) or "").strip().lower()
    if kind in _SYSTEM_STEP_ROLES:
        return kind
    st_id = str(row.survey_type_id or "").strip()
    if st_id:
        st = db.get(SurveyType, st_id)
        if st and str(st.system_template_kind or "").strip().lower() in _SYSTEM_STEP_ROLES:
            return str(st.system_template_kind).strip().lower()
    for mapping in db.execute(
        select(SurveyTypeTemplate, SurveyType)
        .join(SurveyType, SurveyType.id == SurveyTypeTemplate.survey_type_id)
        .where(SurveyTypeTemplate.template_id == row.id)
        .limit(1)
    ).all():
        _mapping, st = mapping
        if st and str(st.system_template_kind or "").strip().lower() in _SYSTEM_STEP_ROLES:
            return str(st.system_template_kind).strip().lower()
    return None


def is_system_survey_template(db: Session, row: TelnyxWhatsappTemplate) -> bool:
    return survey_type_system_kind(db, row) is not None


def should_skip_utility_rewrite(db: Session, row: TelnyxWhatsappTemplate) -> bool:
    return is_system_survey_template(db, row)
