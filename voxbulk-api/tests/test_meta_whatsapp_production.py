"""Meta WhatsApp production routing tests."""

from __future__ import annotations

from app.services.survey_wa_inbound_parse_service import parse_meta_wa_inbound_message


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
