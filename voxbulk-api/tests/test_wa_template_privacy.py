"""Privacy mode for WA survey templates."""

from __future__ import annotations

import pytest

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
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
from app.services.wa_template_privacy import PRIVACY_MODE_OFF, PRIVACY_MODE_ON, normalize_privacy_mode


def _seed_survey_type(db):
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_normalize_privacy_mode_defaults():
    assert normalize_privacy_mode(None) == PRIVACY_MODE_OFF
    assert normalize_privacy_mode("on") == PRIVACY_MODE_ON
    assert normalize_privacy_mode("anonymous") == PRIVACY_MODE_ON
    assert normalize_privacy_mode("off") == PRIVACY_MODE_OFF


def test_validate_rejects_identifying_anonymous_content():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        item = {
            "template_name": "anon_start",
            "variant_type": VARIANT_ANONYMOUS,
            "title": "Anonymous start",
            "step_role": "start",
            "purpose": "start",
            "body": f"Hi {{1}}, {ANONYMOUS_BODY_SENTENCE} Ref {{3}}.",
            "footer": ANONYMOUS_FOOTER,
            "header": "",
            "button_type": "quick_reply",
            "buttons": [{"text": "Start", "url": "", "phone_number": ""}],
            "example_values": ["Alex", "Northgate Dental", "https://example.com/s/1"],
            "language": "en_US",
            "category": "MARKETING",
        }
        normalized, errors = validate_generated_template(item, survey_type=st, privacy_mode=PRIVACY_MODE_ON)
        assert normalized is None
        assert any("{{1}}" in e or "identifying" in e.lower() for e in errors)


def test_save_pack_stores_privacy_mode_separately():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        off_item = {
            "template_name": "std_start",
            "variant_type": VARIANT_STANDARD,
            "title": "Standard start",
            "step_role": "start",
            "purpose": "start",
            "body": "Hi {{1}}, {{2}} would love your feedback.",
            "footer": "Reply STOP to opt out",
            "header": "",
            "button_type": "none",
            "buttons": [],
            "example_values": ["Alex", "Northgate Dental"],
            "language": "en_US",
            "category": "MARKETING",
            "privacy_mode": PRIVACY_MODE_OFF,
        }
        off_result = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st,
            templates=[off_item],
            privacy_mode=PRIVACY_MODE_OFF,
        )
        anon_item = {
            "template_name": "anon_start",
            "variant_type": VARIANT_ANONYMOUS,
            "title": "Anonymous start",
            "step_role": "start",
            "purpose": "start",
            "body": f"{ANONYMOUS_BODY_SENTENCE} Tap below to share feedback with {{2}}.",
            "footer": ANONYMOUS_FOOTER,
            "header": "",
            "button_type": "quick_reply",
            "buttons": [{"text": "Start", "url": "", "phone_number": ""}],
            "example_values": ["Northgate Dental", "https://example.com/s/1"],
            "language": "en_US",
            "category": "MARKETING",
            "privacy_mode": PRIVACY_MODE_ON,
        }
        anon_result = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st,
            templates=[anon_item],
            privacy_mode=PRIVACY_MODE_ON,
        )
        off_bank = load_step_bank(db, survey_type_id=st.id, privacy_mode=PRIVACY_MODE_OFF)
        on_bank = load_step_bank(db, survey_type_id=st.id, privacy_mode=PRIVACY_MODE_ON)
        assert "start" in off_bank["by_role"]
        assert "start" in on_bank["by_role"]
        assert off_bank["by_role"]["start"]["template_id"] != on_bank["by_role"]["start"]["template_id"]
        assert off_result["privacy_mode"] == PRIVACY_MODE_OFF
        assert anon_result["privacy_mode"] == PRIVACY_MODE_ON
        assert off_result["pack_id"] != anon_result["pack_id"]


def test_list_templates_filters_by_privacy_mode():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        row_off = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=st)
        row_off.privacy_mode = PRIVACY_MODE_OFF
        db.add(row_off)
        db.commit()
        row_on = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=st)
        row_on.name = row_on.name.replace("_standard", "_anon_start")
        row_on.variant_type = VARIANT_ANONYMOUS
        row_on.privacy_mode = PRIVACY_MODE_ON
        db.add(row_on)
        db.commit()
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=st.id,
            template_id=row_on.id,
            usable_as_anonymous=True,
            privacy_mode=PRIVACY_MODE_ON,
        )
        off_only = SurveyWhatsappTemplateService.list_for_survey_type(db, st.id, privacy_mode=PRIVACY_MODE_OFF)
        on_only = SurveyWhatsappTemplateService.list_for_survey_type(db, st.id, privacy_mode=PRIVACY_MODE_ON)
        assert all(t["privacy_mode"] == PRIVACY_MODE_OFF for t in off_only)
        assert all(t["privacy_mode"] == PRIVACY_MODE_ON for t in on_only)
