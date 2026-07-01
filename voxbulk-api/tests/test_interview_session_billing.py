from __future__ import annotations

import json

from app.models.service_order import ServiceOrderRecipient
from app.services.interview_session_billing_service import (
    recipient_session_kind,
    summarize_interview_sessions,
    unmetered_billable_minutes,
)


def test_recipient_session_kind_web():
    assert recipient_session_kind({"channel": "meeting", "transport": "webrtc"}) == "web_meeting"


def test_recipient_session_kind_phone():
    assert recipient_session_kind({"channel": "ai_call", "call_control_id": "cc-1"}) == "phone_call"


def test_recipient_session_kind_web_from_config_when_duration_only():
    assert recipient_session_kind({"duration_seconds": 180}, config_delivery="ai_meeting") == "web_meeting"


def test_summarize_interview_sessions_mixed():
    recipients = [
        ServiceOrderRecipient(
            order_id="o1",
            row_number=1,
            name="A",
            result_json=json.dumps({"channel": "meeting", "transport": "webrtc", "billable_minutes": 2}),
        ),
        ServiceOrderRecipient(
            order_id="o1",
            row_number=2,
            name="B",
            result_json=json.dumps({"channel": "ai_call", "duration_seconds": 120, "billable_minutes": 2}),
        ),
    ]
    stats = summarize_interview_sessions(recipients)
    assert stats["interview_format"] == "mixed"
    assert stats["web_sessions"] == 1
    assert stats["phone_sessions"] == 1
    assert stats["total_billable_minutes"] == 4


def test_summarize_interview_web_from_config_without_channel():
    recipients = [
        ServiceOrderRecipient(
            order_id="o1",
            row_number=1,
            name="A",
            result_json=json.dumps({"duration_seconds": 240, "billable_minutes": 4}),
        ),
    ]
    stats = summarize_interview_sessions(recipients, order_config={"delivery": "ai_meeting"})
    assert stats["interview_format"] == "web"
    assert stats["interview_format_label"] == "Web interview"


def test_unmetered_billable_minutes_skips_metered():
    recipients = [
        ServiceOrderRecipient(
            order_id="o1",
            row_number=1,
            name="A",
            result_json=json.dumps({"billable_minutes": 3, "usage_metered_at": "2026-01-01T00:00:00"}),
        ),
        ServiceOrderRecipient(
            order_id="o1",
            row_number=2,
            name="B",
            result_json=json.dumps({"billable_minutes": 2}),
        ),
    ]
    assert unmetered_billable_minutes(recipients) == 2
