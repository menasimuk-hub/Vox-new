"""Tests for WhatsApp survey voice-note open-text handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.survey_wa_inbound_parse_service import NormalizedWaInboundReply, parse_telnyx_wa_inbound_record
from app.services.survey_wa_open_text_service import (
    VOICE_NOTE_FALLBACK_MESSAGE,
    allows_voice_note_answer,
    apply_transcript_to_answer,
    enrich_answer_with_voice_fields,
    is_open_text_question,
    is_voice_message_type,
    resolve_answer_text,
    voice_note_answer_context,
)
from app.services.survey_wa_voice_note_media_service import extract_media_items


def test_is_open_text_question():
    assert is_open_text_question({"reply_type": "long_text"}) is True
    assert is_open_text_question({"reply_type": "rating"}) is False
    assert is_open_text_question({"reply_type": "list"}) is False
    # Stale BUTTONS on tell-us-more row must still count as open-text.
    assert is_open_text_question({"reply_type": "choice", "step_role": "reason", "options": ["Yes", "No"]}) is True


def test_as_open_text_tell_us_more_question_strips_stale_buttons():
    from app.services.survey_builder_flow_service import as_open_text_tell_us_more_question

    q = as_open_text_tell_us_more_question(
        {
            "reply_type": "choice",
            "options": ["Low", "High"],
            "step_role": "reason",
            "text": "Tell us more",
        }
    )
    assert q["reply_type"] == "long_text"
    assert q["options"] == []


@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_prepare_voice_answer_accepts_tell_us_more_with_stale_buttons(mock_enqueue):
    """Tell-us-more with legacy BUTTONS on template row + followup context accepts voice."""
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        extracted_fields={
            "media_items": [{"url": "https://example.com/a.ogg", "provider_media_id": "m1", "content_type": "audio/ogg"}]
        },
    )
    stale_choice_question = {
        "reply_type": "choice",
        "options": ["Yes", "No"],
        "step_role": "reason",
        "text": "Could you tell us more?",
    }

    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            job = MagicMock()
            job.id = "job-tum"
            job.transcription_status = "pending"
            job.audio_file_path = None
            job.audio_mime_type = "audio/ogg"
            job.inbound_message_id = "msg-tum"
            job.provider_media_id = "m1"
            create_job.return_value = job
            result = SurveyWaVoiceNoteService.prepare_voice_answer(
                db,
                order=order,
                recipient=recipient,
                payload={"wa_conversation": {"answers": []}},
                conv={"answers": []},
                question=stale_choice_question,
                reply=reply,
                inbound_message_id="msg-tum",
                log_id=1,
                session_id=None,
                answer_context="followup",
                step_index=2,
                record=None,
                config={},
            )

    assert result.get("rejected") is not True
    assert result["accepted"] is True
    mock_enqueue.assert_called_once_with("job-tum")


@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_prepare_voice_answer_accepts_rating_step_when_tell_us_more_pending(mock_enqueue):
    """Low-rating tell-us-more branch: voice accepted even if step still resolves to rating question."""
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        extracted_fields={
            "media_items": [{"url": "https://example.com/a.ogg", "provider_media_id": "m1", "content_type": "audio/ogg"}]
        },
    )
    rating_question = {"reply_type": "choice", "step_role": "rating", "options": ["Excellent", "Good", "Poor"]}
    conv = {"answers": [{"question": "Rate us", "answer": "Poor"}], "current_node_key": "builder_tell_42"}

    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            job = MagicMock()
            job.id = "job-tum-rating"
            job.transcription_status = "pending"
            job.audio_file_path = None
            job.audio_mime_type = "audio/ogg"
            job.inbound_message_id = "msg-tum-rating"
            job.provider_media_id = "m1"
            create_job.return_value = job
            result = SurveyWaVoiceNoteService.prepare_voice_answer(
                db,
                order=order,
                recipient=recipient,
                payload={"wa_conversation": conv},
                conv=conv,
                question=rating_question,
                reply=reply,
                inbound_message_id="msg-tum-rating",
                log_id=1,
                session_id=None,
                answer_context=voice_note_answer_context(conv=conv, question=rating_question),
                step_index=2,
                record=None,
                config={},
            )

    assert result.get("rejected") is not True
    assert result["accepted"] is True
    assert allows_voice_note_answer(rating_question, answer_context="normal", conv=conv) is True
    mock_enqueue.assert_called_once_with("job-tum-rating")


@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_prepare_voice_accepts_vague_followup_after_what_was_wrong_prompt(mock_enqueue):
    """Auto-followup 'What was wrong with…' must accept voice even if step still looks like rating."""
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        extracted_fields={
            "media_items": [{"url": "https://example.com/a.ogg", "provider_media_id": "m1", "content_type": "audio/ogg"}]
        },
    )
    rating_question = {
        "reply_type": "choice",
        "step_role": "rating",
        "text": "How would you rate the clarity of company news?",
        "options": ["Excellent", "Good", "Poor"],
    }
    conv = {
        "answers": [{"question": rating_question["text"], "answer": "Poor"}],
        "vague_followup_sent_at": "2026-07-05T22:45:00+00:00",
        "followup_for_step": 1,
    }

    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            job = MagicMock()
            job.id = "job-vague"
            job.transcription_status = "pending"
            job.audio_file_path = None
            job.audio_mime_type = "audio/ogg"
            job.inbound_message_id = "msg-vague"
            job.provider_media_id = "m1"
            create_job.return_value = job
            result = SurveyWaVoiceNoteService.prepare_voice_answer(
                db,
                order=order,
                recipient=recipient,
                payload={"wa_conversation": conv},
                conv=conv,
                question=rating_question,
                reply=reply,
                inbound_message_id="msg-vague",
                log_id=1,
                session_id=None,
                answer_context=voice_note_answer_context(conv=conv, question=rating_question),
                step_index=1,
                record=None,
                config={},
            )

    assert result.get("rejected") is not True
    assert result["accepted"] is True
    mock_enqueue.assert_called_once_with("job-vague")


def test_parse_voice_inbound_record():
    record = {
        "type": "whatsapp",
        "whatsapp_message": {
            "type": "audio",
            "media": [{"url": "https://example.com/voice.ogg", "content_type": "audio/ogg", "id": "m1"}],
        },
    }
    reply = parse_telnyx_wa_inbound_record(record, sender_phone="+447700900123")
    assert reply.is_voice_note is True
    assert reply.normalized_answer == ""
    assert reply.extracted_fields["media_items"][0]["provider_media_id"] == "m1"


def test_extract_media_items_dedupes():
    record = {
        "media": [
            {"url": "https://example.com/a.ogg", "id": "same"},
            {"url": "https://example.com/a.ogg", "id": "same"},
        ]
    }
    items = extract_media_items(record)
    assert len(items) == 1


def test_resolve_answer_text_prefers_transcript():
    assert resolve_answer_text({"answer": "old", "answer_text": "transcribed"}) == "transcribed"


def test_enrich_and_apply_transcript():
    pending = enrich_answer_with_voice_fields({"answer": "", "question": "Tell us more"}, job_id="job-1")
    assert pending["transcription_status"] == "pending"
    done = apply_transcript_to_answer(pending, text="  Hello world  ", detected_language="en", status="completed")
    assert done["answer_text"] == "Hello world"
    assert done["detected_language"] == "en"


def test_prepare_voice_answer_rejects_non_open_text():
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        extracted_fields={
            "media_items": [{"url": "https://example.com/a.ogg", "provider_media_id": "m1", "content_type": "audio/ogg"}]
        },
    )
    result = SurveyWaVoiceNoteService.prepare_voice_answer(
        db,
        order=order,
        recipient=recipient,
        payload={"wa_conversation": {"answers": []}},
        conv={"answers": []},
        question={"reply_type": "rating", "text": "Rate us"},
        reply=reply,
        inbound_message_id="msg-1",
        log_id=1,
        session_id=None,
        answer_context="normal",
        step_index=1,
        record=None,
        config={},
    )
    assert result["rejected"] is True
    assert result["fallback_message"] == VOICE_NOTE_FALLBACK_MESSAGE


@patch("app.services.survey_wa_voice_note_service.SurveyWaVoiceNoteService.enqueue_transcription")
def test_prepare_voice_answer_accepts_open_text(mock_enqueue):
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    db = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    order = MagicMock(id="order-1", org_id="org-1")
    recipient = MagicMock(id="recipient-1")
    reply = NormalizedWaInboundReply(
        message_type="audio",
        is_voice_note=True,
        extracted_fields={
            "media_items": [{"url": "https://example.com/a.ogg", "provider_media_id": "m1", "content_type": "audio/ogg"}]
        },
    )

    with patch.object(SurveyWaVoiceNoteService, "find_existing_job", return_value=None):
        with patch.object(SurveyWaVoiceNoteService, "create_pending_job") as create_job:
            job = MagicMock()
            job.id = "job-1"
            job.transcription_status = "pending"
            job.audio_file_path = None
            job.audio_mime_type = "audio/ogg"
            job.inbound_message_id = "msg-1"
            job.provider_media_id = "m1"
            create_job.return_value = job
            result = SurveyWaVoiceNoteService.prepare_voice_answer(
                db,
                order=order,
                recipient=recipient,
                payload={"wa_conversation": {"answers": []}},
                conv={"answers": []},
                question={"reply_type": "long_text", "text": "Tell us more"},
                reply=reply,
                inbound_message_id="msg-1",
                log_id=1,
                session_id=None,
                answer_context="normal",
                step_index=1,
                record=None,
                config={},
            )

    assert result["accepted"] is True
    assert result["answer"]["answer_source"] == "voice_note"
    assert result["answer"]["transcription_status"] == "pending"
    mock_enqueue.assert_called_once_with("job-1")


def test_is_voice_message_type():
    assert is_voice_message_type("audio") is True
    assert is_voice_message_type("text") is False


@pytest.mark.parametrize("status", ["pending", "retrying", "transcribing"])
def test_pending_transcription_skipped_in_aggregates(status):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_results_service import build_answer_aggregates

    recipient = ServiceOrderRecipient(
        id="r1",
        order_id="o1",
        name="Alex",
        phone="+447700900123",
        status="completed",
        result_json='{"extracted_answers":[{"question":"Tell us more","answer":"","answer_source":"voice_note","transcription_status":"'
        + status
        + '"}]}',
    )
    aggregates = build_answer_aggregates([recipient])
    assert len(aggregates) == 1
    assert aggregates[0]["responses"][0]["answer"] == "[Voice note — transcription pending]"


@pytest.mark.parametrize("status", ["pending", "retrying", "transcribing"])
def test_pending_non_voice_transcription_skipped_in_aggregates(status):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_results_service import build_answer_aggregates

    recipient = ServiceOrderRecipient(
        id="r1",
        order_id="o1",
        name="Alex",
        phone="+447700900123",
        status="completed",
        result_json='{"extracted_answers":[{"question":"Tell us more","answer":"","transcription_status":"'
        + status
        + '"}]}',
    )
    aggregates = build_answer_aggregates([recipient])
    assert aggregates == []
