"""Industry scope checks for WA Survey templates and mappings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService


class SurveyIndustryScopeError(ValueError):
    pass


def resolve_survey_type_industry_id(survey_type: SurveyType) -> str:
    industry_id = str(getattr(survey_type, "industry_id", "") or "").strip()
    if not industry_id:
        raise SurveyIndustryScopeError("Survey type must belong to an industry")
    return industry_id


def assert_industry_match(
    *,
    expected_industry_id: str,
    actual_industry_id: str | None,
    message: str = "Industry mismatch — cannot link resources across industries",
) -> None:
    expected = str(expected_industry_id or "").strip()
    actual = str(actual_industry_id or "").strip()
    if expected and actual and expected != actual:
        raise SurveyIndustryScopeError(message)


def apply_industry_to_template(row: TelnyxWhatsappTemplate, survey_type: SurveyType) -> None:
    """Set template industry from survey type. NULL industry is allowed until first link."""
    industry_id = resolve_survey_type_industry_id(survey_type)
    assert_industry_match(
        expected_industry_id=industry_id,
        actual_industry_id=getattr(row, "industry_id", None),
        message="Template industry does not match survey type industry",
    )
    row.industry_id = industry_id
    if not str(row.survey_type_id or "").strip():
        row.survey_type_id = survey_type.id


def mapping_matches_survey_industry(mapping: SurveyTypeTemplate, survey_type: SurveyType) -> bool:
    expected = resolve_survey_type_industry_id(survey_type)
    actual = str(getattr(mapping, "industry_id", "") or "").strip()
    if actual and actual != expected:
        return False
    return True


def template_matches_survey_industry(
    row: TelnyxWhatsappTemplate,
    survey_type: SurveyType,
    *,
    mapping: SurveyTypeTemplate | None = None,
) -> bool:
    """True when template (and optional mapping) belong to the survey type's industry."""
    expected = resolve_survey_type_industry_id(survey_type)
    row_ind = str(getattr(row, "industry_id", "") or "").strip()
    if row_ind and row_ind != expected:
        return False
    if mapping is not None and not mapping_matches_survey_industry(mapping, survey_type):
        return False
    return True


def load_industry_for_prompt(db: Session, survey_type: SurveyType) -> Industry:
    industry_id = resolve_survey_type_industry_id(survey_type)
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise SurveyIndustryScopeError("Survey type industry not found")
    return row
