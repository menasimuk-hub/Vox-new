from __future__ import annotations

import pytest

from seed_data.wa_survey_template_naming import suggest_next_was_seq_name


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        yield session


def test_suggest_next_was_seq_for_convert():
    used = {"was_hotel_overall_001_en"}
    assert suggest_next_was_seq_name("was_hotel_overall_001_en", used_names=used) == "was_hotel_overall_002_en"


def test_convert_save_and_rename_keeps_db_id(db):
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
    from app.services.wa_template_convert_service import save_convert_template, _suggest_survey_next_name
    import json

    row = TelnyxWhatsappTemplate(
        name="was_hotel_overall_001_en",
        language="en_GB",
        category="MARKETING",
        status="APPROVED",
        telnyx_record_id="remote-abc",
        template_id="remote-abc",
        draft_components_json=json.dumps(
            [
                {"type": "BODY", "text": "Please rate your recent stay with us."},
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {"type": "QUICK_REPLY", "text": "Great"},
                        {"type": "QUICK_REPLY", "text": "OK"},
                        {"type": "QUICK_REPLY", "text": "Poor"},
                    ],
                },
            ]
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    tid = row.id

    saved = save_convert_template(
        db,
        product="survey",
        template_id=str(tid),
        body="Please confirm your recent stay feedback for our records.",
        buttons=["Great", "OK", "Poor"],
    )
    assert saved["db_id"] == tid
    assert saved["category"] and str(saved["category"]).upper() == "UTILITY"

    nxt = _suggest_survey_next_name(db, db.get(TelnyxWhatsappTemplate, tid))
    assert nxt == "was_hotel_overall_002_en"

    updated = SurveyWhatsappTemplateService.rename_for_meta_sync(db, db.get(TelnyxWhatsappTemplate, tid), nxt)
    assert updated.id == tid
    assert updated.name == "was_hotel_overall_002_en"
    assert str(updated.status or "").upper() == "LOCAL_DRAFT"


def test_resolve_convert_llm_prefers_deepseek(db, monkeypatch):
    from app.services import wa_template_convert_service as mod

    def fake_get(db, provider):
        if provider == "deepseek":
            return {"api_key": "sk-test", "model": "deepseek-chat"}, True
        return {}, False

    monkeypatch.setattr(
        "app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted",
        fake_get,
    )
    cfg = mod.resolve_convert_llm_config(db)
    assert cfg["provider"] == "deepseek"
    assert cfg["source"] == "deepseek"
