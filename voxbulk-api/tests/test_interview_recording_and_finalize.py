from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_recording_service import (
    USER_RECORDING_PROCESSING,
    USER_RECORDING_UNAVAILABLE,
    fetch_interview_recording,
)
from app.services.interview_session_billing_service import recipient_session_kind


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_recipient_session_kind_webrtc():
    assert recipient_session_kind({"channel": "meeting", "transport": "webrtc"}) == "web_meeting"


def test_fetch_interview_recording_uses_fresh_audio_bytes():
    recipient = ServiceOrderRecipient(
        order_id="ord-1",
        row_number=1,
        name="Test",
        result_json=json.dumps(
            {
                "telnyx_conversation_id": "conv-123",
                "telnyx_recording_download_url": "https://s3.example.com/expired.mp3",
            }
        ),
    )
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()

    fake_rec = {
        "id": "rec-1",
        "format": "mp3",
        "download_url": "https://s3.example.com/fresh.mp3",
        "audio_bytes": b"fake-audio",
    }

    with patch(
        "app.services.interview_recording_service._resolve_from_conversation",
        return_value=fake_rec,
    ):
        result = fetch_interview_recording(db, recipient)

    assert result == (b"fake-audio", "audio/mpeg")


def test_user_recording_messages_hide_provider():
    assert "Telnyx" not in USER_RECORDING_UNAVAILABLE
    assert "Telnyx" not in USER_RECORDING_PROCESSING


def test_complete_meeting_finalizes_order(db_session, monkeypatch):
    from app.models.interview_booking_token import InterviewBookingToken
    from app.models.organisation import Organisation
    from app.services.interview_meeting_service import InterviewMeetingService

    org = Organisation(id=str(uuid.uuid4()), name="Test Org")
    db_session.add(org)
    db_session.flush()

    order = ServiceOrder(
        org_id=org.id,
        user_id=str(uuid.uuid4()),
        service_code="interview",
        title="Test",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps({"delivery": "ai_meeting"}),
    )
    db_session.add(order)
    db_session.flush()

    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Candidate",
        phone="+441234567890",
        status="calling",
        result_json=json.dumps({"channel": "meeting", "transport": "webrtc", "meeting_started_at": "2026-06-29T10:00:00"}),
    )
    db_session.add(recipient)
    db_session.flush()

    token = InterviewBookingToken(
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=org.id,
        token="test-token-abc",
        channel="meeting",
    )
    db_session.add(token)
    db_session.commit()

    finalize_calls: list[str] = []

    def _fake_finalize(db, ord_row):
        finalize_calls.append(ord_row.id)
        ord_row.status = "completed"
        db_session.add(ord_row)
        db_session.commit()
        return ord_row

    monkeypatch.setattr(
        "app.services.interview_call_dispatch_service._finalize_order_if_done",
        _fake_finalize,
    )
    monkeypatch.setattr(
        "app.services.interview_analysis_service.InterviewAnalysisService.process_recipient_post_call",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.interview_meeting_service.schedule_interview_meeting_analysis_retry",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.interview_missed_call_email_service.maybe_send_interview_thank_you_email",
        lambda *a, **k: None,
    )

    result = InterviewMeetingService.complete_meeting(
        db_session,
        "test-token-abc",
        duration_seconds=240,
        provider_call_id="conv-xyz",
    )

    assert result.get("ok") is True
    assert result.get("outcome") == "completed"
    assert finalize_calls == [order.id]
