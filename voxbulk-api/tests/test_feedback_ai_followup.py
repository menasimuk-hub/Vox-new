"""Tests for Customer Feedback AI follow-back scheduling and webhooks."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackAiFollowUpJob, FeedbackLocation, FeedbackSession
from app.models.organisation import Organisation
from app.services.customer_feedback.feedback_ai_followup_service import (
    _build_followup_instructions,
    _callable_phone,
    _format_session_summary_for_prompt,
    _pre_dial_billing_allowed,
    handle_feedback_ai_followup_telnyx_event,
    schedule_if_eligible,
)


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        yield session


def test_callable_phone_rejects_web_sessions():
    assert _callable_phone("+447700900123") is True
    assert _callable_phone("web:051633da-d632-46ba-ab5a-a6b31034a480") is False


def test_format_session_summary_for_prompt():
    text = _format_session_summary_for_prompt(
        {"poor_topics": ["Waiting time"], "positive_topics": ["Staff friendliness"], "no_topics": []}
    )
    assert "Waiting time" in text
    assert "do not re-ask" in text.lower()


def test_build_followup_instructions_includes_recovery_rules():
    job = MagicMock(
        business_context="Family dental clinic",
        promo_enabled=False,
        promo_code="",
        promo_description="",
    )
    _greeting, instructions = _build_followup_instructions(
        job,
        org_name="Acme Dental",
        org_context="Organisation: Acme Dental",
        session_summary={"poor_topics": ["Waiting time"], "positive_topics": [], "no_topics": []},
    )
    assert "recent feedback" in instructions.lower() or "recovery" in instructions.lower()
    assert "Waiting time" in instructions
    assert "recorded" in _greeting.lower()


def test_handle_feedback_ai_followup_telnyx_event_ignores_survey_calls(db: Session):
    payload = {
        "data": {
            "event_type": "call.answered",
            "payload": {
                "call_control_id": "cc-test-1",
                "client_state": json.dumps({"survey_call": True}),
            },
        }
    }
    assert handle_feedback_ai_followup_telnyx_event(db, payload) is False


def test_schedule_if_eligible_skips_web_phone(db: Session):
    org = Organisation(id=str(uuid.uuid4()), name="Test Org", wallet_balance_pence=10_000)
    db.add(org)
    db.flush()

    industry_id = str(uuid.uuid4())
    survey_type_id = str(uuid.uuid4())
    location = FeedbackLocation(
        id=str(uuid.uuid4()),
        org_id=org.id,
        industry_id=industry_id,
        survey_type_id=survey_type_id,
        name="Branch",
        qr_token="test-token-abc123",
        survey_config_json=json.dumps(
            {"ai_follow_up": {"enabled": True, "delay_hours": 24, "business_context": "Test clinic"}}
        ),
    )
    db.add(location)
    db.flush()

    session = FeedbackSession(
        id=str(uuid.uuid4()),
        org_id=org.id,
        location_id=location.id,
        visitor_phone="web:051633da-d632-46ba-ab5a-a6b31034a480",
        status="completed",
    )
    db.add(session)
    db.commit()

    assert schedule_if_eligible(db, session=session, location=location) is False


def test_pre_dial_billing_blocks_low_payg_wallet(db: Session):
    org = Organisation(
        id=str(uuid.uuid4()),
        name="Payg Org",
        wallet_balance_pence=100,
        billing_currency="USD",
    )
    db.add(org)
    db.commit()

    ok, reason, mode = _pre_dial_billing_allowed(db, org)
    assert ok is False
    assert mode == "wallet"
    assert "$5.00" in reason
    assert "£5" not in reason
    assert "$1.00" in reason


def test_pre_dial_billing_allows_promo_wallet_in_org_currency(db: Session):
    org = Organisation(
        id=str(uuid.uuid4()),
        name="Promo Org",
        wallet_balance_pence=2000,
        promo_wallet_balance_pence=2000,
        billing_currency="AUD",
        country_code="AU",
    )
    db.add(org)
    db.commit()

    with patch(
        "app.services.launch_billing_service.LaunchBillingService.estimate_phone_launch",
        return_value={"can_launch": True, "block_reason": None},
    ):
        ok, reason, mode = _pre_dial_billing_allowed(db, org)
    assert ok is True
    assert mode == "payg"
    assert reason == ""


def test_handle_feedback_ai_followup_answered_starts_assistant(db: Session):
    org = Organisation(id=str(uuid.uuid4()), name="Org", wallet_balance_pence=10_000)
    db.add(org)
    job = FeedbackAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=org.id,
        location_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        visitor_phone="+447700900123",
        scheduled_at=datetime.utcnow(),
        status="dispatched",
        call_id="cc-follow-1",
    )
    db.add(job)
    db.commit()

    state = {
        "feedback_ai_followup": True,
        "feedback_ai_followup_job_id": job.id,
        "telnyx_assistant_id": "asst-123",
        "survey_greeting": "Hi there",
        "survey_instructions": "Be kind",
    }
    payload = {
        "data": {
            "event_type": "call.answered",
            "payload": {
                "call_control_id": "cc-follow-1",
                "client_state": json.dumps(state),
            },
        }
    }

    with patch("app.services.telnyx_voice_service.TelnyxVoiceAdapter") as mock_adapter:
        mock_adapter.start_ai_assistant.return_value = MagicMock(ok=True, status="started")
        with patch("app.services.telnyx_voice_service._telnyx_config", return_value={}):
            assert handle_feedback_ai_followup_telnyx_event(db, payload) is True

    db.refresh(job)
    outcome = json.loads(job.outcome_json or "{}")
    assert outcome.get("assistant_started_at")
    mock_adapter.start_ai_assistant.assert_called_once()


def test_amd_hangs_up_and_schedules_retry(db: Session):
    from app.services.customer_feedback.feedback_ai_followup_service import _try_schedule_followup_retry

    org = Organisation(id=str(uuid.uuid4()), name="Org", wallet_balance_pence=10_000)
    db.add(org)
    job = FeedbackAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=org.id,
        location_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        visitor_phone="+447700900999",
        scheduled_at=datetime.utcnow(),
        status="dispatched",
        call_id="cc-amd-1",
    )
    db.add(job)
    db.commit()

    state = {
        "feedback_ai_followup": True,
        "feedback_ai_followup_job_id": job.id,
        "telnyx_assistant_id": "asst-123",
    }
    payload = {
        "data": {
            "event_type": "call.machine.detection.ended",
            "payload": {
                "call_control_id": "cc-amd-1",
                "result": "machine",
                "client_state": json.dumps(state),
            },
        }
    }

    with (
        patch("app.services.telnyx_voice_service.TelnyxVoiceAdapter") as mock_adapter,
        patch("app.services.telnyx_voice_service._telnyx_config", return_value={}),
        patch(
            "app.services.survey_call_dispatch_service._is_voicemail_telnyx_event",
            return_value=True,
        ),
        patch(
            "app.services.customer_feedback.feedback_ai_followup_service._next_calling_window_utc",
            return_value=datetime.utcnow(),
        ),
    ):
        mock_adapter.hangup_call.return_value = MagicMock(ok=True)
        assert handle_feedback_ai_followup_telnyx_event(db, payload) is True

    db.refresh(job)
    assert job.status == "scheduled"
    outcome = json.loads(job.outcome_json or "{}")
    assert outcome.get("voicemail_detected") is True
    assert int(outcome.get("retry_count") or 0) == 1
    mock_adapter.hangup_call.assert_called_once()


def test_no_answer_hangup_schedules_retry_then_terminal(db: Session):
    org = Organisation(id=str(uuid.uuid4()), name="Org", wallet_balance_pence=10_000)
    db.add(org)
    job = FeedbackAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=org.id,
        location_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        visitor_phone="+447700900888",
        scheduled_at=datetime.utcnow(),
        status="dispatched",
        call_id="cc-na-1",
        outcome_json=json.dumps({"retry_count": 0}),
    )
    db.add(job)
    db.commit()

    state = {
        "feedback_ai_followup": True,
        "feedback_ai_followup_job_id": job.id,
    }
    payload = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "cc-na-1",
                "hangup_cause": "no_answer",
                "client_state": json.dumps(state),
            },
        }
    }

    with (
        patch(
            "app.services.customer_feedback.feedback_ai_followup_service._settle_followup_call_billing",
            return_value={},
        ),
        patch(
            "app.services.customer_feedback.feedback_ai_followup_service._next_calling_window_utc",
            return_value=datetime.utcnow(),
        ),
        patch("app.services.telnyx_voice_service._telnyx_config", return_value={}),
    ):
        assert handle_feedback_ai_followup_telnyx_event(db, payload) is True

    db.refresh(job)
    assert job.status == "scheduled"
    assert int(json.loads(job.outcome_json or "{}").get("retry_count") or 0) == 1

    # Second no-answer exhausts retries → terminal no_answer
    job.status = "dispatched"
    db.add(job)
    db.commit()
    payload2 = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "cc-na-2",
                "hangup_cause": "no_answer",
                "client_state": json.dumps(state),
            },
        }
    }
    with (
        patch(
            "app.services.customer_feedback.feedback_ai_followup_service._settle_followup_call_billing",
            return_value={},
        ),
        patch("app.services.telnyx_voice_service._telnyx_config", return_value={}),
    ):
        assert handle_feedback_ai_followup_telnyx_event(db, payload2) is True

    db.refresh(job)
    assert job.status == "no_answer"
