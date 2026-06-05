"""Admin global system templates API."""

from __future__ import annotations

import pytest

from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_system_template_service import (
    SYSTEM_TEMPLATE_KINDS,
    SurveySystemTemplateService,
    normalize_system_template_kind,
)
from app.services.survey_type_service import SurveyTypeService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

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


def test_ensure_system_survey_types(db):
    types = SurveySystemTemplateService.ensure_system_survey_types(db)
    kinds = {t.system_template_kind for t in types}
    assert kinds == set(SYSTEM_TEMPLATE_KINDS)


def test_create_draft_welcome(db):
    result = SurveySystemTemplateService.create_draft(db, kind="welcome", payload={"display_name": "Warm welcome"})
    assert result["ok"] is True
    assert result["template"]["display_name"] == "Warm welcome"
    grouped = SurveySystemTemplateService.list_grouped_admin(db)
    assert grouped["templates"]["welcome"]


def test_normalize_kind_rejects_invalid():
    with pytest.raises(Exception):
        normalize_system_template_kind("invalid")
