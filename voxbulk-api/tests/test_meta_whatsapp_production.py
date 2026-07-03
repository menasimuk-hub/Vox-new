"""Meta WhatsApp production routing tests."""

from __future__ import annotations

import json

import pytest

from app.core.database import get_sessionmaker
from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_wa_inbound_parse_service import parse_meta_wa_inbound_message
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService


def test_parse_meta_text_inbound():
    reply = parse_meta_wa_inbound_message(
        {"type": "text", "text": {"body": "Hello clinic"}},
        sender_phone="+447700900123",
    )
    assert reply.normalized_answer == "Hello clinic"
    assert reply.message_type == "text"


def test_parse_meta_button_reply():
    reply = parse_meta_wa_inbound_message(
        {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "start_survey", "title": "Start survey"},
            },
        },
        sender_phone="+447700900123",
    )
    assert reply.button_title == "Start survey"
    assert reply.normalized_action == "start_survey"


def test_parse_meta_quick_button():
    reply = parse_meta_wa_inbound_message(
        {"type": "button", "button": {"text": "Yes", "payload": "yes_payload"}},
        sender_phone="+447700900123",
    )
    assert reply.normalized_answer == "Yes"
    assert reply.button_payload == "yes_payload"


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_push_to_meta_when_primary(monkeypatch):
    with get_sessionmaker()() as db:
        SurveyTypeService.ensure_defaults(db)
        survey_type = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
        assert survey_type is not None
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        meta_item = {
            "id": "meta-12345",
            "name": row.name,
            "language": "en_US",
            "category": "UTILITY",
            "status": "PENDING",
            "components": json.loads(row.draft_components_json),
            "telnyx_record_id": "meta-12345",
            "template_id": "meta-12345",
        }

        monkeypatch.setattr(
            "app.services.whatsapp_provider_service.is_meta_whatsapp_primary",
            lambda _db: True,
        )
        monkeypatch.setattr(
            MetaWhatsappTemplateService,
            "push_template_payload",
            lambda _db, **kwargs: meta_item,
        )
        monkeypatch.setattr(
            MetaWhatsappTemplateService,
            "fetch_by_record_id",
            lambda _db, _rid: meta_item,
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_remote_templates",
            lambda _db: [],
        )

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert result["ok"] is True
        db.refresh(row)
        assert str(row.telnyx_record_id or "").startswith("meta-")
