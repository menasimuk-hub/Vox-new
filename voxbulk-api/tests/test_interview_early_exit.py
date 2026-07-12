"""Early-exit classification for interview sessions."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from app.services.interview_early_exit_service import classify_interview_session_outcome


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


def test_not_free_is_reschedule():
    assert (
        classify_interview_session_outcome(
            duration_seconds=60,
            transcript="I'm not free right now, can I reschedule the appointment?",
        )
        == "reschedule"
    )


def test_recording_declined_is_hard_stop():
    assert (
        classify_interview_session_outcome(
            duration_seconds=40,
            transcript="No I don't consent to being recorded.",
        )
        == "recording_declined"
    )


def test_wrong_person_early():
    assert (
        classify_interview_session_outcome(
            duration_seconds=25,
            transcript="Sorry, wrong person, you have the wrong number.",
        )
        == "wrong_person"
    )


def test_short_silent_is_technical_abort():
    assert classify_interview_session_outcome(duration_seconds=40, transcript="") == "technical_abort"


def test_ambiguous_short_is_reschedule():
    assert classify_interview_session_outcome(duration_seconds=100, transcript="") == "reschedule"


def test_mid_interview_stop_stays_completed():
    long_transcript = (
        "First question: tell me about your experience. "
        "I worked five years in retail managing a team. "
        "Next question: can you describe a challenge you solved? "
        "We had stock issues and I fixed the process. "
        "I need to stop now and reschedule for later please."
    )
    assert (
        classify_interview_session_outcome(duration_seconds=240, transcript=long_transcript)
        == "completed"
    )


def test_short_mid_interview_stop_stays_completed():
    """Q&A markers must win even when transcript is under the 220-char heuristic."""
    short = (
        "First question: tell me about your experience. I worked five years. "
        "Next question: describe a challenge. We fixed stock. I need to reschedule later."
    )
    assert len(short) < 220
    assert (
        classify_interview_session_outcome(duration_seconds=240, transcript=short)
        == "completed"
    )


def test_session_signals_mark_progress():
    assert (
        classify_interview_session_outcome(
            duration_seconds=90,
            transcript="I need to reschedule later please.",
            session_signals={"questions_asked": 2},
        )
        == "completed"
    )


def test_ar_mid_interview_stop_stays_completed():
    text = (
        "السؤال الأول خبرتك إيه؟ اشتغلت خمس سنين. "
        "السؤال التالي صف لي تحدي. صلحنا المخزون. محتاج إعادة جدولة."
    )
    assert (
        classify_interview_session_outcome(duration_seconds=200, transcript=text)
        == "completed"
    )


def test_long_call_reschedule_without_questions_is_reschedule():
    """Layer 2: duration alone must not force completed when transcript shows reschedule."""
    transcript = (
        "Hello is this Alex? Yes. This is Leo calling about the interview. "
        "Is now a good time? I'm not free, can I reschedule the appointment please? "
        "No problem, use the link in your email. Goodbye."
    )
    assert (
        classify_interview_session_outcome(duration_seconds=240, transcript=transcript)
        == "reschedule"
    )


def test_substantial_duration_completed_without_transcript():
    assert classify_interview_session_outcome(duration_seconds=200, transcript=None) == "completed"


def test_admin_unlock_completed_booking(db_session):
    from app.models.interview_booking_token import InterviewBookingToken
    from app.models.organisation import Organisation
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.interview_booking_service import (
        admin_unlock_interview_booking,
        interview_booking_locked,
    )

    org = Organisation(id=str(uuid.uuid4()), name="Org")
    db_session.add(org)
    db_session.flush()
    order = ServiceOrder(
        org_id=org.id,
        user_id=str(uuid.uuid4()),
        service_code="interview",
        title="Role",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps({"delivery": "ai_call", "role": "Host"}),
    )
    db_session.add(order)
    db_session.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        email="alex@example.com",
        phone="+441111",
        status="completed",
        result_json=json.dumps(
            {
                "session_outcome": "completed",
                "ended_at": "2026-07-12T00:00:00",
                "analysis_saved_at": "2026-07-12T00:01:00",
            }
        ),
    )
    db_session.add(recipient)
    db_session.flush()
    db_session.add(
        InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=org.id,
            token=f"unlock-token-{uuid.uuid4().hex[:8]}",
            channel="ai_call",
            booked_start_at=None,
        )
    )
    db_session.commit()
    assert interview_booking_locked(recipient) is not None

    with patch(
        "app.services.interview_session_outcome_email_service.dispatch_interview_session_outcome_email",
        return_value={"ok": True},
    ):
        result = admin_unlock_interview_booking(
            db_session,
            order=order,
            recipient=recipient,
            reason="test_unlock",
            send_reschedule_email=True,
        )
    assert result["ok"] is True
    db_session.refresh(recipient)
    assert recipient.status == "pending"
    assert interview_booking_locked(recipient) is None


def test_reclassify_unlocks_completed_after_transcript(db_session):
    from app.models.interview_booking_token import InterviewBookingToken
    from app.models.organisation import Organisation
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.interview_booking_service import interview_booking_locked
    from app.services.interview_early_exit_service import (
        maybe_reclassify_completed_interview_after_transcript,
    )

    org = Organisation(id=str(uuid.uuid4()), name="Org")
    db_session.add(org)
    db_session.flush()
    order = ServiceOrder(
        org_id=org.id,
        user_id=str(uuid.uuid4()),
        service_code="interview",
        title="Role",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps({"delivery": "ai_meeting", "role": "Host"}),
    )
    db_session.add(order)
    db_session.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        email="alex@example.com",
        phone="+441111",
        status="completed",
        result_json=json.dumps(
            {
                "channel": "meeting",
                "duration_seconds": 210,
                "session_outcome": "completed",
                "session_outcome_provisional": True,
                "ended_at": "2026-07-12T00:00:00",
                "transcript": (
                    "Hi, is this Alex? Yes. Is now a good time? "
                    "I'm not free can I reschedule please? Okay use the email link. Bye."
                ),
            }
        ),
    )
    db_session.add(recipient)
    db_session.flush()
    db_session.add(
        InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=org.id,
            token=f"reclass-token-{uuid.uuid4().hex[:8]}",
            channel="meeting",
            booked_start_at=None,
        )
    )
    db_session.commit()

    with patch(
        "app.services.interview_early_exit_service._send_reschedule_email",
        return_value=True,
    ):
        result = maybe_reclassify_completed_interview_after_transcript(
            db_session, order=order, recipient=recipient
        )
    assert result is not None
    assert result.get("outcome") == "reschedule"
    db_session.refresh(recipient)
    assert recipient.status == "pending"
    assert interview_booking_locked(recipient) is None
