"""Missed-call follow-up email — agent-configured template and voicemail policy."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.agent import AgentDefinition
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_missed_call_email_service import (
    maybe_send_interview_missed_call_email,
    missed_call_email_report_payload,
    resolve_missed_call_email_template_key,
    should_send_missed_call_followup_email,
)
from app.services.interview_report_data_service import InterviewCandidateReportService
from app.services.interview_report_template import build_candidate_report_html


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    yield


def _seed(*, agent_kwargs: dict | None = None):
    with get_sessionmaker()() as db:
        org = Organisation(name="Missed Call Org")
        db.add(org)
        db.flush()
        user = User(email=f"mc-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        agent_defaults = {
            "name": "Interview Agent",
            "slug": f"interview-agent-{uuid.uuid4().hex[:8]}",
            "system_prompt": "You conduct interviews.",
            "supports_interview": True,
            "is_default_interview": True,
            "voicemail_behavior": "hang_up",
        }
        agent_defaults.update(agent_kwargs or {})
        agent = AgentDefinition(**agent_defaults)
        db.add(agent)
        db.flush()
        now = datetime.utcnow()
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="interview",
            title="Engineer",
            status="running",
            payment_status="approved",
            scheduled_start_at=now,
            scheduled_end_at=now + timedelta(hours=8),
            config_json=json.dumps(
                {
                    "delivery": "ai_call",
                    "role": "Engineer",
                    "agent_id": agent.id,
                }
            ),
        )
        db.add(order)
        db.flush()
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Alex Candidate",
            phone="+447700900123",
            email="alex@example.com",
            status="no_answer",
            result_json=json.dumps({"booking_url": "https://book.example/slot-1"}),
        )
        db.add(recipient)
        db.flush()
        token = InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=org.id,
            token="book-" + uuid.uuid4().hex,
        )
        db.add(token)
        db.commit()
        return db, org, order, recipient, agent


def test_should_send_respects_voicemail_policy():
    ok, reason = should_send_missed_call_followup_email(
        terminal_status="no_answer",
        voicemail_detected=True,
        voicemail_behavior="hang_up",
    )
    assert ok is True
    assert reason is None

    ok, reason = should_send_missed_call_followup_email(
        terminal_status="no_answer",
        voicemail_detected=True,
        voicemail_behavior="leave_message",
    )
    assert ok is False
    assert reason == "voicemail_message_left"

    ok, reason = should_send_missed_call_followup_email(
        terminal_status="busy",
        voicemail_detected=True,
        voicemail_behavior="retry_later",
    )
    assert ok is False
    assert reason == "retry_scheduled"

    ok, reason = should_send_missed_call_followup_email(
        terminal_status="completed",
        voicemail_detected=False,
        voicemail_behavior="hang_up",
    )
    assert ok is False
    assert reason == "not_missed_terminal"


def test_resolve_template_key_from_agent():
    agent = AgentDefinition(
        name="A",
        slug="a",
        system_prompt="x",
        missed_call_email_template_interview="interview_booking_invite",
    )
    assert resolve_missed_call_email_template_key(agent) == "interview_booking_invite"
    agent.missed_call_email_template_interview = "none"
    assert resolve_missed_call_email_template_key(agent) is None
    agent.missed_call_email_template_interview = None
    assert resolve_missed_call_email_template_key(agent) == "interview_missed_call_followup"


def test_send_missed_call_email_uses_agent_template(monkeypatch):
    db, _org, order, recipient, agent = _seed(
        agent_kwargs={"missed_call_followup_notes_interview": "Custom follow-up copy for Alex."}
    )
    send = MagicMock(return_value=(True, None))
    monkeypatch.setattr(
        "app.services.interview_missed_call_email_service.CareerEmailService.send_templated_optional",
        send,
    )
    result = maybe_send_interview_missed_call_email(
        db,
        order=order,
        recipient=recipient,
        agent=agent,
        terminal_status="no_answer",
        voicemail_detected=True,
        voicemail_behavior="hang_up",
    )
    assert result["ok"] is True
    send.assert_called_once()
    assert send.call_args.kwargs["template_key"] == "interview_missed_call_followup"
    assert send.call_args.kwargs["variables"]["followup_message"] == "Custom follow-up copy for Alex."
    db.refresh(recipient)
    parsed = json.loads(recipient.result_json)
    assert parsed["missed_call_email_ok"] is True
    assert parsed["missed_call_email_template"] == "interview_missed_call_followup"
    assert parsed["missed_call_experience_notes"] == "Custom follow-up copy for Alex."


def test_skips_email_for_leave_message_voicemail():
    db, _org, order, recipient, agent = _seed(agent_kwargs={"voicemail_behavior": "leave_message"})
    result = maybe_send_interview_missed_call_email(
        db,
        order=order,
        recipient=recipient,
        agent=agent,
        terminal_status="no_answer",
        voicemail_detected=True,
        voicemail_behavior="leave_message",
    )
    assert result["skipped"] is True
    assert result["reason"] == "voicemail_message_left"
    parsed = json.loads(recipient.result_json)
    assert parsed["missed_call_email_skip_reason"] == "voicemail_message_left"


def test_skips_when_template_disabled_on_agent():
    db, _org, order, recipient, agent = _seed(
        agent_kwargs={"missed_call_email_template_interview": "none"}
    )
    result = maybe_send_interview_missed_call_email(
        db,
        order=order,
        recipient=recipient,
        agent=agent,
        terminal_status="no_answer",
        voicemail_detected=False,
        voicemail_behavior="hang_up",
    )
    assert result["skipped"] is True
    assert result["reason"] == "template_disabled"


def test_idempotent_second_send():
    db, _org, order, recipient, agent = _seed()
    recipient.result_json = json.dumps({"missed_call_email_sent_at": "2026-01-01T12:00:00"})
    db.add(recipient)
    db.commit()
    result = maybe_send_interview_missed_call_email(
        db,
        order=order,
        recipient=recipient,
        agent=agent,
        terminal_status="no_answer",
    )
    assert result["skipped"] is True
    assert result["reason"] == "already_sent"


def test_report_payload_and_html_include_call_outcome():
    db, _org, order, recipient, agent = _seed(
        agent_kwargs={
            "missed_call_followup_notes_interview": "We will call back at your chosen slot.",
            "voicemail_behavior": "hang_up",
        }
    )
    recipient.result_json = json.dumps(
        {
            "missed_call_email_ok": True,
            "missed_call_email_sent_at": "2026-06-01T10:00:00",
            "missed_call_email_template": "interview_missed_call_followup",
            "missed_call_email_to": "alex@example.com",
            "missed_call_voicemail_behavior": "hang_up",
            "missed_call_experience_notes": "We will call back at your chosen slot.",
            "voicemail_detected": True,
        }
    )
    db.add(recipient)
    db.commit()
    parsed = json.loads(recipient.result_json)
    call_outcome = missed_call_email_report_payload(db, order=order, recipient=recipient, parsed=parsed)
    assert call_outcome["voicemail_behavior_label"] == "Hang up for now"
    assert call_outcome["missed_call_email"]["outcome_label"] == "Follow-up email sent"
    assert "We will call back" in call_outcome["experience_notes"]

    payload = InterviewCandidateReportService.build_payload(db, order, recipient)
    assert payload["call_outcome"]["missed_call_email"]["outcome_label"] == "Follow-up email sent"
    html = build_candidate_report_html(payload, for_pdf=False)
    assert "Call Outcome" in html
    assert "Follow-up email sent" in html
    assert "We will call back at your chosen slot." in html


def test_agent_api_persists_missed_call_fields(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    created = app_client.post(
        "/admin/agents",
        json={
            "name": "Missed Call Agent",
            "slug": f"missed-call-{uuid.uuid4().hex[:8]}",
            "system_prompt": "Interview agent.",
            "supports_interview": True,
            "telnyx_assistant_id": "assistant-test",
            "missed_call_email_template_interview": "interview_missed_call_followup",
            "missed_call_followup_notes_interview": "Book a slot when you can.",
        },
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["missed_call_email_template_interview"] == "interview_missed_call_followup"
    assert body["missed_call_followup_notes_interview"] == "Book a slot when you can."
