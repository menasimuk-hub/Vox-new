"""WA Survey industry dimension — persistence, filtering, and cross-industry guards."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.survey_template_pack import SurveyTemplatePack
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.survey_industry_scope import SurveyIndustryScopeError
from app.services.survey_step_bank_service import load_step_bank
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_wa_template_pack_service import SurveyWaTemplatePackService, validate_generated_template
from app.services.survey_whatsapp_template_service import (
    ANONYMOUS_BODY_SENTENCE,
    ANONYMOUS_FOOTER,
    SurveyWhatsappTemplateService,
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
)
from app.services.wa_template_privacy import PRIVACY_MODE_OFF, PRIVACY_MODE_ON


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _sample_item(**overrides):
    base = {
        "template_name": "std_intro",
        "variant_type": VARIANT_STANDARD,
        "title": "Standard intro",
        "step_role": "start",
        "purpose": "intro",
        "body": "Hi {{1}}, {{2}} would love your feedback. Ref {{3}}.",
        "footer": "Reply STOP to opt out",
        "header": "",
        "button_type": "quick_reply",
        "buttons": [{"text": "Start survey", "url": "", "phone_number": ""}],
        "example_values": ["Alex", "Northgate Dental", "https://example.com/s/1"],
        "language": "en_US",
        "category": "MARKETING",
    }
    base.update(overrides)
    return base


def test_industry_seed_and_survey_type_filter(db=None):
    Session = get_sessionmaker()
    with Session() as db:
        industries = IndustryService.list_industries(db)
        assert len(industries) >= 7
        healthcare = IndustryService.get_by_slug(db, "healthcare")
        assert healthcare is not None

        SurveyTypeService.ensure_defaults(db)
        all_types = SurveyTypeService.list_types(db)
        assert any(t["slug"] == "customer_satisfaction" for t in all_types)

        hc_types = SurveyTypeService.list_types(db, industry_id=healthcare.id)
        assert all(t["industry_id"] == healthcare.id for t in hc_types)

        ecommerce = IndustryService.get_by_slug(db, "ecommerce")
        row = SurveyTypeService.create_type(
            db,
            {"name": "Ecom pulse", "slug": "ecom_pulse", "industry_id": ecommerce.id},
        )
        assert row.industry_id == ecommerce.id
        filtered = SurveyTypeService.list_types(db, industry_id=ecommerce.id)
        assert any(t["id"] == row.id for t in filtered)
        assert not any(t["id"] == row.id for t in hc_types)


def test_pack_save_persists_industry_and_privacy():
    Session = get_sessionmaker()
    with Session() as db:
        healthcare = IndustryService.get_by_slug(db, "healthcare")
        ecommerce = IndustryService.get_by_slug(db, "ecommerce")
        st_hc = SurveyTypeService.create_type(
            db,
            {"name": "HC CSAT", "slug": "hc_csat", "industry_id": healthcare.id},
        )
        st_ec = SurveyTypeService.create_type(
            db,
            {"name": "EC CSAT", "slug": "ec_csat", "industry_id": ecommerce.id},
        )

        item = _sample_item()
        saved_hc = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st_hc,
            templates=[item],
            privacy_mode=PRIVACY_MODE_OFF,
            industry_id=healthcare.id,
        )
        tpl_id = int(saved_hc["templates"][0]["id"])
        tpl = db.get(TelnyxWhatsappTemplate, tpl_id)
        assert tpl is not None
        assert tpl.industry_id == healthcare.id
        pack = db.get(SurveyTemplatePack, saved_hc["pack_id"])
        assert pack is not None
        assert pack.industry_id == healthcare.id

        with pytest.raises(Exception):
            SurveyWaTemplatePackService.save_selected_templates(
                db,
                survey_type=st_hc,
                templates=[_sample_item(template_name="other_tpl")],
                industry_id=ecommerce.id,
            )


def test_step_bank_excludes_other_industry_templates():
    Session = get_sessionmaker()
    with Session() as db:
        healthcare = IndustryService.get_by_slug(db, "healthcare")
        ecommerce = IndustryService.get_by_slug(db, "ecommerce")
        st_hc = SurveyTypeService.create_type(
            db,
            {"name": "HC Bank", "slug": "hc_bank", "industry_id": healthcare.id},
        )
        st_ec = SurveyTypeService.create_type(
            db,
            {"name": "EC Bank", "slug": "ec_bank", "industry_id": ecommerce.id},
        )

        roles = [
            "start",
            "rating",
            "yes_no",
            "helpfulness",
            "abc_choice",
            "reason",
            "feeling_word",
            "follow_up",
            "improvement",
            "completion",
        ]
        SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st_hc,
            templates=[
                _sample_item(template_name=f"hc_{role}", step_role=role) for role in roles
            ],
            privacy_mode=PRIVACY_MODE_OFF,
        )

        wrong = _sample_item(template_name="ec_start", step_role="start")
        result_ec = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st_ec,
            templates=[wrong],
            privacy_mode=PRIVACY_MODE_OFF,
        )
        ec_tpl_id = int(result_ec["templates"][0]["id"])
        mapping = SurveyTypeTemplate(
            industry_id=healthcare.id,
            survey_type_id=st_hc.id,
            template_id=ec_tpl_id,
            usable_as_standard=True,
            privacy_mode=PRIVACY_MODE_OFF,
        )
        db.add(mapping)
        db.commit()

        bank = load_step_bank(db, survey_type_id=st_hc.id, privacy_mode=PRIVACY_MODE_OFF)
        ids = {i["template_id"] for i in bank["items"]}
        assert ec_tpl_id not in ids
        assert "start" in bank["by_role"]


def test_cross_industry_mapping_rejected():
    Session = get_sessionmaker()
    with Session() as db:
        healthcare = IndustryService.get_by_slug(db, "healthcare")
        ecommerce = IndustryService.get_by_slug(db, "ecommerce")
        st_hc = SurveyTypeService.create_type(
            db,
            {"name": "HC Link", "slug": "hc_link", "industry_id": healthcare.id},
        )
        st_ec = SurveyTypeService.create_type(
            db,
            {"name": "EC Link", "slug": "ec_link", "industry_id": ecommerce.id},
        )
        saved = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st_ec,
            templates=[_sample_item(template_name="ec_only")],
            privacy_mode=PRIVACY_MODE_OFF,
        )
        tpl_id = int(saved["templates"][0]["id"])
        with pytest.raises(SurveyIndustryScopeError):
            SurveyTypeTemplateService.upsert_mapping(
                db,
                survey_type_id=st_hc.id,
                template_id=tpl_id,
                usable_as_standard=True,
            )


def test_privacy_banks_stay_separate_per_industry():
    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.default_industry(db)
        st = SurveyTypeService.create_type(
            db,
            {"name": "Privacy split", "slug": "privacy_split", "industry_id": industry.id},
        )
        off_item = _sample_item(template_name="id_start", step_role="start")
        on_item = _sample_item(
            template_name="anon_start",
            step_role="start",
            variant_type=VARIANT_ANONYMOUS,
            body=f"{ANONYMOUS_BODY_SENTENCE} How was your visit at {{2}}?",
            footer=ANONYMOUS_FOOTER,
            example_values=["Northgate Dental", "https://example.com/s/1"],
        )
        SurveyWaTemplatePackService.save_selected_templates(
            db, survey_type=st, templates=[off_item], privacy_mode=PRIVACY_MODE_OFF
        )
        SurveyWaTemplatePackService.save_selected_templates(
            db, survey_type=st, templates=[on_item], privacy_mode=PRIVACY_MODE_ON
        )
        off_list = SurveyWhatsappTemplateService.list_for_survey_type(db, st.id, privacy_mode=PRIVACY_MODE_OFF)
        on_list = SurveyWhatsappTemplateService.list_for_survey_type(db, st.id, privacy_mode=PRIVACY_MODE_ON)
        assert len(off_list) == 1
        assert len(on_list) == 1
        assert off_list[0]["privacy_mode"] == PRIVACY_MODE_OFF
        assert on_list[0]["privacy_mode"] == PRIVACY_MODE_ON
        assert off_list[0]["id"] != on_list[0]["id"]


def test_create_survey_type_requires_industry():
    Session = get_sessionmaker()
    with Session() as db:
        with pytest.raises(ValueError, match="industry"):
            SurveyTypeService.create_type(db, {"name": "No industry", "slug": "no_industry"})
