"""WhatsApp quick-reply handling for interview booking."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_whatsapp_inbound_service import (
    find_active_booking_context,
    handle_inbound_reply,
    parse_interview_booking_intent,
)


def _seed_booking(db, *, booked: bool = False):
    org = Organisation(name="WA Inbound Org")
    db.add(org)
    db.flush()
    user = User(email=f"wa-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    now = datetime.utcnow()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        status="running",
        payment_status="approved",
        scheduled_start_at=now,
        scheduled_end_at=now + timedelta(hours=4),
        config_json='{"delivery":"ai_call","role":"Engineer"}',
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex Demo",
        phone="+447700900123",
        status="sent",
    )
    db.add(recipient)
    db.flush()
    slot = now + timedelta(hours=1)
    token = InterviewBookingToken(
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=org.id,
        token="wa-test-" + uuid.uuid4().hex,
        wa_sent_at=now,
        booked_start_at=slot if booked else None,
        booked_end_at=slot + timedelta(minutes=30) if booked else None,
    )
    db.add(token)
    db.commit()
    return org, order, recipient, token


def test_parse_interview_booking_intent():
    assert parse_interview_booking_intent("❌ Cancel") == "cancel"
    assert parse_interview_booking_intent("🔄 Reschedule") == "reschedule"
    assert parse_interview_booking_intent("📅 Book My Interview") == "book"
    assert parse_interview_booking_intent("I can't make it") == "cancel"
    assert parse_interview_booking_intent("need to cancel") == "cancel"
    assert parse_interview_booking_intent("Can I change my time?") == "reschedule"
    assert parse_interview_booking_intent("hello") is None


def test_find_active_booking_context_by_phone():
    with get_sessionmaker()() as db:
        org, _, recipient, token = _seed_booking(db, booked=True)
        ctx = find_active_booking_context(db, from_phone=recipient.phone, org_id=org.id)
        assert ctx is not None
        assert ctx[0].id == token.id


def test_handle_cancel_booking(monkeypatch):
    sent: list[str] = []
    emails: list[str] = []

    def fake_send(db, **kwargs):
        sent.append(kwargs["body"])

        class Result:
            ok = True

        return Result()

    def fake_email(db, **kwargs):
        emails.append(kwargs.get("template_key"))
        return True, None

    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.send_whatsapp",
        lambda db, **kwargs: fake_send(db, **kwargs),
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.log_outbound",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
        lambda db, **kwargs: fake_email(db, **kwargs),
    )

    with get_sessionmaker()() as db:
        org, _, recipient, token = _seed_booking(db, booked=True)
        recipient.email = "alex@example.com"
        db.add(recipient)
        db.commit()
        result = handle_inbound_reply(
            db,
            from_phone=recipient.phone,
            body="❌ Cancel",
            org_id=org.id,
        )
        assert result["handled"] is True
        assert result["action"] == "cancelled"
        db.refresh(token)
        db.refresh(recipient)
        assert token.booked_start_at is None
        assert sent and "cancelled" in sent[0].lower()
        assert "interview_booking_cancel" in emails
        merged = json.loads(recipient.result_json or "{}")
        assert merged.get("booking_cancelled_via") == "whatsapp"


def test_handle_reschedule_sends_link(monkeypatch):
    sent: list[str] = []

    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.send_whatsapp",
        lambda db, **kwargs: sent.append(kwargs["body"]) or type("R", (), {"ok": True})(),
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.log_outbound",
        lambda *a, **k: None,
    )

    with get_sessionmaker()() as db:
        org, _, recipient, _ = _seed_booking(db, booked=True)
        result = handle_inbound_reply(
            db,
            from_phone=recipient.phone,
            body="🔄 Reschedule",
            org_id=org.id,
        )
        assert result["handled"] is True
        assert result["action"] == "reschedule_link"
        assert sent and "reschedule=1" in sent[0]
