"""Tests for WA Survey template cleanup and Tell Us More flow fixes."""

from __future__ import annotations

import pytest

from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_step_bank_service import normalize_step_role
from app.services.survey_system_template_service import SurveySystemTemplateService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_wa_template_cleanup_service import cleanup_wa_survey_templates, template_should_keep
from app.services.survey_wa_template_pack_service import validate_generated_template
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
        SurveySystemTemplateService.ensure_system_industry(session)
        SurveySystemTemplateService.ensure_system_survey_types(session)
        yield session
    finally:
        session.close()


def test_normalize_step_role_maps_tell_us_more_to_reason():
    assert normalize_step_role("tell_us_more") == "reason"


def test_validate_generated_accepts_tell_us_more_purpose(db):
    survey_type = SurveySystemTemplateService.survey_type_for_kind(db, "tell_us_more")
    normalized, errors = validate_generated_template(
        {
            "template_name": "tell_us_more_variant_1",
            "title": "Tell us more",
            "body": "Sorry to hear that. What could we improve?",
            "footer": "Reply STOP to opt out",
            "button_type": "none",
            "buttons": [],
            "example_values": ["there"],
            "language": "en_US",
            "category": "UTILITY",
            "purpose": "tell_us_more",
            "variant_type": "standard",
        },
        survey_type=survey_type,
        privacy_mode="off",
        purpose="tell_us_more",
    )
    assert not errors
    assert normalized is not None
    assert normalized["step_role"] == "reason"


def test_save_generated_tell_us_more_appears_in_grouped_list(db):
    payload = {
        "template_name": "tell_us_more_variant_1",
        "title": "Tell us more",
        "body": "Sorry to hear that. What could we improve?",
        "footer": "Reply STOP to opt out",
        "button_type": "none",
        "buttons": [],
        "example_values": ["there"],
        "language": "en_US",
        "category": "UTILITY",
        "purpose": "tell_us_more",
        "variant_type": "standard",
    }
    result = SurveySystemTemplateService.save_generated(db, kind="tell_us_more", templates=[payload])
    assert result.get("saved_count", 0) >= 1
    grouped = SurveySystemTemplateService.list_grouped_admin(db)
    assert grouped["templates"]["tell_us_more"]


def test_cleanup_keeps_system_and_hospitality_only(db):
    hospitality = IndustryService.get_by_slug(db, "hospitality_food")
    healthcare = IndustryService.get_by_slug(db, "healthcare")
    assert hospitality is not None
    assert healthcare is not None

    hc_type = SurveyTypeService.create_type(
        db,
        {"name": "HC Cleanup", "slug": "hc_cleanup_type", "industry_id": healthcare.id},
    )
    hosp_type = SurveyTypeService.create_type(
        db,
        {"name": "Hosp Cleanup", "slug": "hosp_cleanup_type", "industry_id": hospitality.id},
    )
    hc_tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=hc_type)
    hosp_tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=hosp_type)
    system_type = SurveySystemTemplateService.survey_type_for_kind(db, "welcome")
    system_tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=system_type)

    assert template_should_keep(db, hc_tpl) is False
    assert template_should_keep(db, hosp_tpl) is True
    assert template_should_keep(db, system_tpl) is True

    preview = cleanup_wa_survey_templates(db, dry_run=True, update_category_to_utility=False)
    deleted_ids = {row["id"] for row in preview["deleted"]}
    kept_ids = {row["id"] for row in preview["kept"]}
    assert int(hc_tpl.id) in deleted_ids
    assert int(hosp_tpl.id) in kept_ids
    assert int(system_tpl.id) in kept_ids


def test_attach_tell_us_more_graph_builds_low_rating_branch(db):
    from app.services.survey_tell_us_more_flow_service import attach_tell_us_more_graph, inject_reason_step_into_composed

    composed = {
        "page_roles": ["start", "rating", "yes_no", "completion"],
        "pages": [],
        "whatsapp_flow": {
            "questions": [
                {"step_role": "rating", "text": "Rate us", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
                {"step_role": "yes_no", "text": "Recommend?", "reply_type": "true_false", "options": ["Yes", "No"]},
            ],
            "page_roles": ["start", "rating", "yes_no", "completion"],
        },
    }
    tell_type = SurveySystemTemplateService.survey_type_for_kind(db, "tell_us_more")
    tell_tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=tell_type)
    tell_tpl.step_role = "reason"
    tell_tpl.body_preview = "Please tell us more."
    db.add(tell_tpl)
    db.commit()

    composed = inject_reason_step_into_composed(
        composed,
        tell_us_more_template_id=tell_tpl.id,
        db=db,
    )
    extras = attach_tell_us_more_graph(
        composed=composed,
        survey_type_id="test-type",
        privacy_mode="off",
        page_count=4,
        closing_body="Thanks",
        max_question_visits=4,
    )
    assert extras["flow_engine"] == "graph"
    snap = extras["flow_snapshot"]
    assert snap
    assert "reason" in [str(r) for r in composed["page_roles"]]
    branch_targets = [
        edge.get("to_node_key")
        for edge in snap.get("edges") or []
        if edge.get("from_node_key") == "rating" and edge.get("condition_json")
    ]
    assert "reason" in branch_targets
