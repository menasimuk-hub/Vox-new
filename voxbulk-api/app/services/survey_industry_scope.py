"""Industry scope checks for WA Survey templates and mappings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
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
    industry_id = resolve_survey_type_industry_id(survey_type)
    assert_industry_match(
        expected_industry_id=industry_id,
        actual_industry_id=getattr(row, "industry_id", None),
        message="Template industry does not match survey type industry",
    )
    row.industry_id = industry_id


def load_industry_for_prompt(db: Session, survey_type: SurveyType) -> Industry:
    industry_id = resolve_survey_type_industry_id(survey_type)
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise SurveyIndustryScopeError("Survey type industry not found")
    return row
