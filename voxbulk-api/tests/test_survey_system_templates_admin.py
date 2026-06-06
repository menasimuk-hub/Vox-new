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
    normalize_system_generated_item,
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


def test_save_generated_appears_in_grouped_welcome(db):
    payload = {
        "template_name": "welcome_warm_start",
        "title": "Warm welcome",
        "body": "Hi {{1}}, welcome to our short survey.",
        "footer": "Reply STOP to opt out",
        "button_type": "quick_reply",
        "buttons": [{"text": "Start survey", "url": "", "phone_number": ""}],
        "example_values": ["Alex"],
        "language": "en_US",
        "category": "MARKETING",
        "step_role": "start",
        "variant_type": "standard",
    }
    result = SurveySystemTemplateService.save_generated(db, kind="welcome", templates=[payload])
    assert result.get("saved_count", 0) >= 1
    grouped = SurveySystemTemplateService.list_grouped_admin(db)
    assert grouped["templates"]["welcome"]
    welcome_kind = next(item for item in grouped["kinds"] if item["kind"] == "welcome")
    assert welcome_kind["count"] == len(grouped["templates"]["welcome"])


def test_selectable_industries_exclude_hidden_system_industry(db):
    from app.services.industry_service import IndustryService, SYSTEM_SURVEY_INDUSTRY_SLUG

    selectable = IndustryService.list_industries_selectable(db)
    slugs = {row["slug"] for row in selectable}
    assert SYSTEM_SURVEY_INDUSTRY_SLUG not in slugs
    admin_all = IndustryService.list_industries_admin(db, include_hidden=True, include_inactive=True)
    assert any(row["slug"] == SYSTEM_SURVEY_INDUSTRY_SLUG for row in admin_all)


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


def test_normalize_system_generated_item_repairs_empty_body():
    fixed = normalize_system_generated_item({"title": "Thank you"}, kind="thank_you", idx=0)
    assert fixed["body"]
    assert fixed["example_values"]
    assert fixed["outcome_key"] == "neutral"


def test_generate_with_openai_repairs_sparse_openai_rows(db, monkeypatch):
    from app.services.survey_wa_template_pack_service import _build_pack_item_row

    sparse = {
        "template_name": "bad",
        "variant_type": "standard",
        "title": "Draft thank you",
        "step_role": "completion",
        "outcome_key": "neutral",
        "purpose": "thank_you",
        "body": "",
        "footer": "",
        "header": "",
        "button_type": "none",
        "buttons": [],
        "example_values": [],
        "language": "en_US",
        "category": "MARKETING",
    }

    def fake_responses_json(db, **kwargs):
        return {"templates": [sparse, {**sparse, "title": "Second"}]}, {"model": "test"}

    monkeypatch.setattr(
        "app.services.survey_system_template_service.OpenAIProviderService.responses_json",
        fake_responses_json,
    )

    result = SurveySystemTemplateService.generate_with_openai(db, kind="thank_you", count=2)
    assert result["valid_count"] >= 1
    first = result["templates"][0]
    assert first["valid"] is True
    assert first["template"]["body"]
    assert first["template"]["example_values"]


def test_hide_template_sets_active_for_survey_false(db):
    SurveySystemTemplateService.ensure_system_survey_types(db)
    result = SurveySystemTemplateService.create_draft(db, kind="welcome", payload={"display_name": "Warm welcome"})
    tpl_id = result["template"]["id"]
    row = SurveyWhatsappTemplateService.get_template(db, tpl_id)
    assert row is not None
    assert row.active_for_survey is True

    updated = SurveyWhatsappTemplateService.save_draft(db, row, {"active_for_survey": False})
    assert updated.active_for_survey is False

    restored = SurveyWhatsappTemplateService.save_draft(db, updated, {"active_for_survey": True})
    assert restored.active_for_survey is True
