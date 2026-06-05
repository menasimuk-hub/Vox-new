"""Admin global system templates API."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.models.survey_type_template import SurveyTypeTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_system_template_service import (
    SYSTEM_TEMPLATE_KINDS,
    SurveySystemTemplateService,
    normalize_system_template_kind,
)
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService


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


def test_orphan_system_template_appears_in_grouped_list(db):
    survey_type = SurveySystemTemplateService.survey_type_for_kind(db, "welcome")
    row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
    row.display_name = "Orphan welcome"
    db.add(row)
    db.commit()
    grouped = SurveySystemTemplateService.list_grouped_admin(db)
    ids = {item["id"] for item in grouped["templates"]["welcome"]}
    assert int(row.id) in ids


def test_create_draft_noname_variant(db):
    result = SurveySystemTemplateService.create_draft(
        db,
        kind="welcome",
        payload={"display_name": "Quiet welcome", "privacy_mode": "on"},
    )
    assert result["template"]["variant_label"] == "Noname"
    grouped = SurveySystemTemplateService.list_grouped_admin(db)
    labels = {item["variant_label"] for item in grouped["templates"]["welcome"]}
    assert "Noname" in labels


def test_normalize_kind_rejects_invalid():
    with pytest.raises(Exception):
        normalize_system_template_kind("invalid")


def test_system_generate_schema_is_openai_strict():
    from app.services.survey_wa_template_pack_service import build_system_template_json_schema

    schema = SurveySystemTemplateService._system_generate_schema(2)
    build_system_template_json_schema(2)
    assert schema.get("additionalProperties") is False
    assert schema.get("required") == ["templates"]

    items = schema["properties"]["templates"]["items"]
    assert items.get("type") == "object"
    assert items.get("additionalProperties") is False
    assert set(items.get("required") or []) == set(items.get("properties") or {})

    button_items = items["properties"]["buttons"]["items"]
    assert button_items.get("additionalProperties") is False
    assert set(button_items.get("required") or []) == set(button_items.get("properties") or {})
