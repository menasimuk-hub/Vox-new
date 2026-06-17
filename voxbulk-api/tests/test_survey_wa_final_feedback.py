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
    FINAL_FEEDBACK_TEXT_TIMEOUT_SEC,
    begin_final_feedback_open_text,
    build_final_feedback_branch,
    final_feedback_settings,
    is_awaiting_final_feedback,
    is_bare_yes_no_reply,
    persist_final_feedback_text,
    process_final_feedback_timeouts,
    runtime_final_feedback_enabled,
)
from app.services.survey_wa_inbound_parse_service import NormalizedWaInboundReply
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply, _try_voice_note_reply


def _voice_inbound_reply(message_id: str = "msg-voice-1") -> NormalizedWaInboundReply:
    return NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        normalized_answer="",
        extracted_fields={
            "media_items": [
                {
                    "url": "https://example.com/voice.ogg",
                    "provider_media_id": "media-1",
                    "content_type": "audio/ogg",
                }
            ]
        },
    )


def _mock_pending_voice_job(create_job):
    job = MagicMock()
    job.id = "job-final-1"
    job.transcription_status = "pending"
    job.audio_file_path = "/tmp/voice.ogg"
    job.audio_mime_type = "audio/ogg"
    job.inbound_message_id = "msg-voice-1"
    job.provider_media_id = "media-1"
    create_job.return_value = job
    return job


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
    assert conv.get("final_feedback_text_deadline")
    assert is_awaiting_final_feedback(conv) is True


def test_is_bare_yes_no_reply():
    assert is_bare_yes_no_reply("Yes") == "Yes"
    assert is_bare_yes_no_reply("No") == "No"
    assert is_bare_yes_no_reply("Parking was difficult") is None
    assert is_bare_yes_no_reply("Yes, the queue was long") is None


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
    yes_no = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_final_feedback_global_final_feedback_voice_note",
        display_name="Final feedback yes/no",
        language="en_US",
        category="MARKETING",
        body_preview="Would you like to add anything else before we finish?",
        step_role="yes_no",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps(
            [
                {"type": "BODY", "text": "Would you like to add anything else before we finish?"},
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {"type": "QUICK_REPLY", "text": "Yes"},
                        {"type": "QUICK_REPLY", "text": "No"},
                    ],
                },
            ]
        ),
    )
    db.add_all([welcome, rating, thank, yes_no])
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
def test_final_feedback_sends_yes_no_before_open_text(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)

    assert result.get("final_feedback") == "awaiting_yes_no"
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    conv = payload.get("wa_conversation") or {}
    assert conv.get("awaiting_final_feedback_yes_no") is True
    assert conv.get("awaiting_final_feedback_text") is not True
    sent_names = [str(c.kwargs.get("template_name") or "") for c in mock_send.call_args_list]
    assert "voxbulk_survey_final_feedback_global_final_feedback_voice_note" in sent_names
    sent_bodies = [str(c.kwargs.get("body") or "") for c in mock_send.call_args_list]
    assert not any(DEFAULT_OPEN_TEXT_PROMPT in body for body in sent_bodies)


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_final_feedback_no_skips_to_thank_you(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)
    result = handle_inbound_reply(db, from_phone=recipient.phone, body="No", org_id=org_id)

    assert result.get("completed") is True
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload.get("final_feedback_yes_no") == "No"
    assert payload.get("final_additional_feedback") in (None, "")


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_final_feedback_yes_then_text_completes(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)
    handle_inbound_reply(db, from_phone=recipient.phone, body="Yes", org_id=org_id)
    final = handle_inbound_reply(db, from_phone=recipient.phone, body="Parking was difficult", org_id=org_id)

    assert final.get("completed") is True
    assert final.get("reason") != "final_feedback_yes_no_unparsed"
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload.get("final_additional_feedback") == "Parking was difficult"
    conv = payload.get("wa_conversation") or {}
    assert conv.get("final_feedback_done") is True


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_legacy_yes_no_state_parses_yes_then_open_text(mock_send, db):
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

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="Yes", org_id=org_id)

    assert result.get("final_feedback") == "awaiting_open_text"
    db.refresh(recipient)
    saved = json.loads(recipient.result_json or "{}")
    assert saved.get("final_feedback_yes_no") == "Yes"
    assert saved["wa_conversation"].get("awaiting_final_feedback_text") is True


@patch("app.services.survey_wa_voice_note_settings.voice_notes_enabled", return_value=True)
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_final_feedback_voice_on_yes_no_completes(mock_enqueue, mock_send, _voice_enabled, db):
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)
    voice = _voice_inbound_reply()
    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            _mock_pending_voice_job(create_job)
            result = handle_inbound_reply(
                db,
                from_phone=recipient.phone,
                body="",
                org_id=org_id,
                inbound_message_id="msg-voice-1",
                inbound_reply=voice,
            )

    assert result.get("completed") is True
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload.get("final_feedback_yes_no") == "Yes"
    roles = [a.get("step_role") for a in payload["wa_conversation"]["answers"]]
    assert "final_feedback_text" in roles
    assert payload["wa_conversation"].get("final_feedback_done") is True
    mock_enqueue.assert_called_once_with("job-final-1")


@patch("app.services.survey_wa_voice_note_settings.voice_notes_enabled", return_value=True)
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_final_feedback_yes_then_voice_completes(mock_enqueue, mock_send, _voice_enabled, db):
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    order, recipient, org_id = _seed_final_feedback_order(db, org.id)

    handle_inbound_reply(db, from_phone=recipient.phone, body="8", org_id=org_id)
    handle_inbound_reply(db, from_phone=recipient.phone, body="Yes", org_id=org_id)
    voice = _voice_inbound_reply("msg-voice-2")
    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            _mock_pending_voice_job(create_job)
            result = handle_inbound_reply(
                db,
                from_phone=recipient.phone,
                body="",
                org_id=org_id,
                inbound_message_id="msg-voice-2",
                inbound_reply=voice,
            )

    assert result.get("completed") is True
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload.get("final_feedback_yes_no") == "Yes"
    text_answers = [a for a in payload["wa_conversation"]["answers"] if a.get("step_role") == "final_feedback_text"]
    assert len(text_answers) == 1
    assert text_answers[0].get("answer_source") == "voice_note"


@patch("app.services.survey_wa_voice_note_settings.voice_notes_enabled", return_value=True)
def test_try_voice_note_reply_duplicate_keeps_accepted(_voice_enabled):
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = _voice_inbound_reply()
    with patch.object(
        SurveyWaVoiceNoteService,
        "prepare_voice_answer",
        return_value={
            "accepted": True,
            "duplicate": True,
            "job_id": "job-dup",
            "transcript_ready": False,
            "answer": {"answer_source": "voice_note", "transcription_status": "pending"},
        },
    ):
        result = _try_voice_note_reply(
            db,
            order=order,
            recipient=recipient,
            payload={"wa_conversation": {"answers": []}},
            conv={"answers": []},
            question={"reply_type": "long_text", "step_role": "final_feedback_text"},
            reply=reply,
            inbound_message_id="msg-dup",
            log_id=1,
            session_id=None,
            answer_context="final_feedback",
            step_index=2,
            config={},
        )

    assert result is not None
    assert result.get("accepted") is True
    assert result.get("duplicate") is True


def _seed_tell_us_more_open_question(db, org_id: str):
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
    tell = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="tell_us_more",
        display_name="Tell us more",
        language="en_US",
        category="MARKETING",
        body_preview=DEFAULT_OPEN_TEXT_PROMPT,
        step_role="reason",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": DEFAULT_OPEN_TEXT_PROMPT}]),
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
    db.add_all([welcome, rating, tell, thank])
    db.commit()

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[rating.id],
        tell_us_more_template_id=tell.id,
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
        title="Tell us more Yes gate",
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
        phone="+447700900456",
        status="in_progress",
        result_json=json.dumps(
            {
                "wa_conversation": {
                    "step": 2,
                    "total": 3,
                    "intro_sent_at": "2026-01-01T00:00:00",
                    "tell_us_more_pending": True,
                    "answers": [
                        {
                            "step_role": "rating",
                            "question": "Rate us",
                            "answer": "2",
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
def test_tell_us_more_open_question_yes_awaits_voice_text(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Tell Us More Org")
    db.add(org)
    db.commit()
    _order, recipient, org_id = _seed_tell_us_more_open_question(db, org.id)

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="Yes", org_id=org_id)

    assert result.get("final_feedback") == "awaiting_open_text"
    assert result.get("completed") is not True
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    conv = payload.get("wa_conversation") or {}
    assert conv.get("awaiting_final_feedback_text") is True
    assert conv.get("final_feedback_text_deadline")
    assert not conv.get("tell_us_more_pending")
    sent_bodies = [str(c.kwargs.get("body") or "") for c in mock_send.call_args_list]
    assert any(DEFAULT_OPEN_TEXT_PROMPT in body for body in sent_bodies)


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_awaiting_open_text_bare_yes_reprompts(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    _order, recipient, org_id = _seed_final_feedback_order(db, org.id)
    payload = json.loads(recipient.result_json or "{}")
    begin_final_feedback_open_text(payload["wa_conversation"])
    recipient.result_json = json.dumps(payload)
    db.add(recipient)
    db.commit()

    result = handle_inbound_reply(db, from_phone=recipient.phone, body="Yes", org_id=org_id)

    assert result.get("final_feedback") == "open_text_reprompt"
    assert result.get("completed") is not True
    db.refresh(recipient)
    saved = json.loads(recipient.result_json or "{}")
    assert saved["wa_conversation"].get("awaiting_final_feedback_text") is True
    assert saved.get("final_additional_feedback") in (None, "")


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_final_feedback_text_timeout_sends_thank_you(mock_send, db):
    from datetime import datetime, timedelta, timezone

    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Final Feedback Org")
    db.add(org)
    db.commit()
    _order, recipient, org_id = _seed_final_feedback_order(db, org.id)
    payload = json.loads(recipient.result_json or "{}")
    conv = payload["wa_conversation"]
    conv["awaiting_final_feedback_text"] = True
    conv["final_feedback_yes_no"] = "Yes"
    conv["final_feedback_text_deadline"] = (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    ).isoformat()
    recipient.result_json = json.dumps(payload)
    db.add(recipient)
    db.commit()

    count = process_final_feedback_timeouts(db)

    assert count == 1
    db.refresh(recipient)
    saved = json.loads(recipient.result_json or "{}")
    assert str(recipient.status).lower() == "completed"
    assert saved.get("final_additional_feedback") in (None, "")
    assert "final_feedback_text_deadline" not in (saved.get("wa_conversation") or {})
    assert mock_send.call_count >= 1


def test_final_feedback_text_timeout_sec_constant():
    assert FINAL_FEEDBACK_TEXT_TIMEOUT_SEC == 60
