"""Tests for optional final additional feedback before thank-you."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_flow_service import ensure_question_display_name
from app.services.survey_builder_runtime_service import attach_builder_runtime_to_config, build_builder_runtime, resolve_runtime_step
from app.services.survey_wa_final_feedback_service import (
    DEFAULT_OPEN_TEXT_PROMPT,
    DEFAULT_YES_NO_QUESTION,
    begin_final_feedback_open_text,
    build_final_feedback_branch,
    final_feedback_settings,
    is_awaiting_final_feedback,
    persist_final_feedback_text,
    runtime_final_feedback_enabled,
)
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply


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
        yield session
    finally:
        session.close()


def test_final_feedback_defaults_off():
    assert runtime_final_feedback_enabled({}) is False
    settings = final_feedback_settings({})
    assert settings["enabled"] is False
    assert settings["yes_no_question"] == DEFAULT_YES_NO_QUESTION
    assert settings["open_text_prompt"] == DEFAULT_OPEN_TEXT_PROMPT


def test_final_feedback_enabled_from_config():
    cfg = {
        "allow_final_additional_feedback": True,
        "builder_runtime": {
            "branches": {
                "final_additional_feedback": build_final_feedback_branch(enabled=True),
            }
        },
    }
    assert runtime_final_feedback_enabled(cfg) is True


def test_begin_final_feedback_open_text_state():
    conv: dict = {"awaiting_final_feedback_yes_no": True}
    begin_final_feedback_open_text(conv)
    assert conv.get("awaiting_final_feedback_text") is True
    assert "awaiting_final_feedback_yes_no" not in conv
    assert is_awaiting_final_feedback(conv) is True


def test_persist_final_feedback_text_fields():
    payload: dict = {"wa_conversation": {"answers": []}}
    settings = final_feedback_settings({"allow_final_additional_feedback": True})
    persist_final_feedback_text(payload, text="Staff were rude", settings=settings)
    assert payload["final_additional_feedback"] == "Staff were rude"
    roles = [a.get("step_role") for a in payload["wa_conversation"]["answers"]]
    assert roles == ["final_feedback_text"]
    assert any(item.get("final_additional_feedback") for item in payload["extracted_answers"])


def test_builder_runtime_step_one_display_name(db):
    welcome = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome_tpl",
        display_name="Welcome",
        language="en_US",
        category="MARKETING",
        body_preview="Hi {{1}}",
        step_role="start",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Hi {{1}}"}]),
    )
    rating = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="",
        display_name="",
        language="en_US",
        category="MARKETING",
        body_preview="Rate us",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Rate us"}]),
    )
    thank = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="thanks",
        display_name="Thanks",
        language="en_US",
        category="MARKETING",
        body_preview="Thanks",
        step_role="completion",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Thanks"}]),
    )
    db.add_all([welcome, rating, thank])
    db.commit()

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[rating.id],
        thank_you_template_id=thank.id,
        allow_final_additional_feedback=True,
    )
    config = attach_builder_runtime_to_config({"delivery": "whatsapp"}, runtime)
    step1 = resolve_runtime_step(config, 1)
    assert step1["display_name"] == "Rate us"

    fallback = ensure_question_display_name({"step_role": "rating", "text": "Any comments?"}, sequence=1, survey_type_name="")
    assert fallback["display_name"] == "Any comments?"


def _seed_final_feedback_order(db, org_id: str):
    welcome = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome",
        display_name="Welcome",
        language="en_US",
        category="MARKETING",
        body_preview="Hi {{1}}",
        step_role="start",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Hi {{1}}"}]),
    )
    rating = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="rating",
        display_name="Rating",
        language="en_US",
        category="MARKETING",
        body_preview="Rate {{1}}",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Rate {{1}}"}]),
    )
    thank = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="thank_you",
        display_name="Thank you",
        language="en_US",
        category="MARKETING",
        body_preview="Thanks {{1}}",
        step_role="completion",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Thanks {{1}}"}]),
    )
    db.add_all([welcome, rating, thank])
    db.commit()

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[rating.id],
        thank_you_template_id=thank.id,
        allow_final_additional_feedback=True,
    )
    config = attach_builder_runtime_to_config(
        {
            "delivery": "whatsapp",
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "wa_template_id": welcome.id,
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id="user-1",
        service_code="survey",
        title="Final feedback test",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
    )
    db.add(order)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900123",
        status="in_progress",
        result_json=json.dumps(
            {
                "wa_conversation": {
                    "step": 1,
                    "intro_sent_at": "2026-01-01T00:00:00",
                    "answers": [
                        {
                            "step_role": "rating",
                            "question": "Rate us",
                            "answer": "8",
                            "reply_type": "choice",
                        }
                    ],
                }
            }
        ),
    )
    db.add(recipient)
    db.commit()
    return order, recipient, org_id


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_final_feedback_sends_open_text_prompt_not_yes_no(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)

    assert result.get("final_feedback") == "awaiting_open_text"
    assert result.get("reason") != "final_feedback_yes_no_unparsed"
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    conv = payload.get("wa_conversation") or {}
    assert conv.get("awaiting_final_feedback_text") is True
    assert conv.get("awaiting_final_feedback_yes_no") is not True
    sent_bodies = [str(c.kwargs.get("body") or "") for c in mock_send.call_args_list]
    assert any(DEFAULT_OPEN_TEXT_PROMPT in body for body in sent_bodies)
    assert not any(DEFAULT_YES_NO_QUESTION in body for body in sent_bodies)


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_final_feedback_text_reply_completes(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)
    final = handle_inbound_reply(db, from_phone=recipient.phone, body="Parking was difficult", org_id=org_id)

    assert final.get("completed") is True
    assert final.get("reason") != "final_feedback_yes_no_unparsed"
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload.get("final_additional_feedback") == "Parking was difficult"
    conv = payload.get("wa_conversation") or {}
    assert conv.get("final_feedback_done") is True


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_legacy_yes_no_state_accepts_text_as_final_feedback(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)
    payload = json.loads(recipient.result_json or "{}")
    payload["wa_conversation"]["awaiting_final_feedback_yes_no"] = True
    recipient.result_json = json.dumps(payload)
    db.add(recipient)
    db.commit()

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="More time with the hygienist", org_id=org_id)

    assert result.get("completed") is True
    assert result.get("reason") != "final_feedback_yes_no_unparsed"
    db.refresh(recipient)
    saved = json.loads(recipient.result_json or "{}")
    assert saved.get("final_additional_feedback") == "More time with the hygienist"
