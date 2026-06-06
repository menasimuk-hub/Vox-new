"""Bulk WA Survey library template generation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_wa_bulk_library_template_service import (
    DEFAULT_LIBRARY_STEP_ROLE,
    SurveyWaBulkLibraryTemplateService,
)
from app.services.survey_wa_template_pack_service import SurveyWaTemplatePackService
from app.services.survey_whatsapp_template_service import VARIANT_STANDARD


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    from app.services.industry_service import IndustryService
    from app.services.platform_catalog_service import PlatformCatalogService
    from app.services.survey_type_service import SurveyTypeService

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        IndustryService.ensure_defaults(session)
        SurveyTypeService.ensure_defaults(session)
        SurveyIndustrySeedService.ensure_catalog(session)
        yield session
    finally:
        session.close()


def _seed_catalog(db):
    SurveyIndustrySeedService.ensure_catalog(db)
    targets = list(SurveyWaBulkLibraryTemplateService.iter_targets(db))
    assert targets, "expected seeded industry survey types"
    return targets[0]


def _rating_template_payload(*, name: str = "food_quality_rating"):
    return {
        "template_name": name,
        "variant_type": VARIANT_STANDARD,
        "title": "Food quality",
        "step_role": "rating",
        "outcome_key": None,
        "purpose": "food quality",
        "body": "Hi {{1}} 👋 How would you rate the food quality from your recent visit?",
        "footer": "Reply STOP to opt out",
        "header": "",
        "button_type": "none",
        "buttons": [],
        "example_values": ["Alex"],
        "language": "en_US",
        "category": "MARKETING",
    }


def test_iter_targets_excludes_system_industry_and_kinds(db):
    SurveyIndustrySeedService.ensure_catalog(db)
    targets = list(SurveyWaBulkLibraryTemplateService.iter_targets(db))
    assert targets
    for target in targets:
        assert not target.industry.is_hidden
        assert target.survey_type.system_template_kind is None


def test_duplicate_detection_skips_existing(db):
    target = _seed_catalog(db)
    survey_type = target.survey_type
    row = SurveyWaTemplatePackService._create_draft_row(
        db,
        survey_type=survey_type,
        item=_rating_template_payload(),
        privacy_mode="off",
    )
    db.commit()

    existing = SurveyWaBulkLibraryTemplateService.find_existing_library_template(
        db,
        survey_type=survey_type,
        step_role=DEFAULT_LIBRARY_STEP_ROLE,
    )
    assert existing is not None
    assert existing.id == row.id

    result = SurveyWaBulkLibraryTemplateService.process_target(
        db,
        target=target,
        step_role=DEFAULT_LIBRARY_STEP_ROLE,
        dry_run=False,
        overwrite=False,
    )
    assert result.status == "skipped"
    assert result.template_id == row.id


@patch("app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json")
def test_bulk_creates_local_draft(mock_openai, db):
    target = _seed_catalog(db)
    mock_openai.return_value = ({"template": _rating_template_payload()}, {"model": "test"})

    result = SurveyWaBulkLibraryTemplateService.process_target(
        db,
        target=target,
        step_role=DEFAULT_LIBRARY_STEP_ROLE,
        dry_run=False,
        overwrite=False,
    )
    assert result.status == "created"
    assert result.template_id

    tpl = db.get(TelnyxWhatsappTemplate, result.template_id)
    assert tpl is not None
    assert str(tpl.status).upper() == "LOCAL_DRAFT"
    assert tpl.survey_type_id == target.survey_type.id
    assert tpl.industry_id == target.industry.id
    mappings = SurveyTypeTemplateService.list_for_survey_type(db, target.survey_type.id)
    assert any(m.template_id == tpl.id for m in mappings)


@patch("app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json")
def test_dry_run_does_not_call_openai(mock_openai, db):
    target = _seed_catalog(db)
    payload = SurveyWaBulkLibraryTemplateService.run_bulk(
        db,
        dry_run=True,
        limit=1,
        industry_slug=target.industry.slug,
        survey_type_slug=target.survey_type.slug,
    )
    mock_openai.assert_not_called()
    assert payload["summary"]["dry_run"] == 1
    assert payload["results"][0].status == "dry_run"


def test_generate_library_template_rejects_system_survey_type(db):
    SurveyIndustrySeedService.ensure_catalog(db)
    from sqlalchemy import select

    from app.models.survey_type import SurveyType
    from app.services.survey_system_template_service import SurveySystemTemplateService

    SurveySystemTemplateService.ensure_system_survey_types(db)
    st = db.execute(
        select(SurveyType).where(SurveyType.system_template_kind == "welcome").limit(1)
    ).scalar_one()
    with pytest.raises(Exception, match="system survey types"):
        SurveyWaTemplatePackService.generate_library_template(db, survey_type=st)
