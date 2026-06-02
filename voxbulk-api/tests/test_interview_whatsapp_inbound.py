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
from app.services.interview_booking_service import SLOT_MINUTES
from app.services.interview_whatsapp_inbound_service import (
    find_active_booking_context,
    handle_inbound_reply,
    parse_interview_booking_intent,
)
from app.services.interview_booking_service import InterviewBookingService


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
        booked_end_at=slot + timedelta(minutes=SLOT_MINUTES) if booked else None,
    )
    db.add(token)
    db.commit()
    return org, order, recipient, token


def test_parse_interview_booking_intent():
    assert parse_interview_booking_intent("❌ Cancel") == "cancel"
    assert parse_interview_booking_intent("🛑 Cancel") == "cancel"
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
        "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
        lambda db, **kwargs: fake_send(db, **kwargs),
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
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
        assert result.get("sent") is True
        db.refresh(token)
        db.refresh(recipient)
        assert token.booked_start_at is None
        assert recipient.status == "pending"
        assert sent and "cancelled" in sent[0].lower()
        assert "will not receive" in sent[0].lower()
        assert "interview_booking_cancel" in emails
        merged = json.loads(recipient.result_json or "{}")
        assert merged.get("booking_cancelled_via") == "whatsapp"
        assert merged.get("cancellation_email_sent_at")
        assert merged.get("cancellation_wa_sent_at")


def test_handle_cancel_uses_stored_invite_booking_url(monkeypatch):
    sent: list[str] = []
    invite_url = "https://book.voxbulk.com/book/wa-test-invite-link"

    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.send_whatsapp",
        lambda db, **kwargs: sent.append(kwargs["body"]) or type("R", (), {"ok": True})(),
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_inbound_service.TelnyxMessagingService.log_outbound",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
        lambda db, **kwargs: (True, None),
    )

    with get_sessionmaker()() as db:
        org, _, recipient, token = _seed_booking(db, booked=True)
        recipient.email = "alex@example.com"
        recipient.result_json = json.dumps(
            {
                "booking_token": token.token,
                "booking_url": invite_url,
                "invite_email_sent_at": datetime.utcnow().isoformat(),
            }
        )
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
        assert sent
        assert invite_url not in sent[0]
        assert "will not receive" in sent[0].lower()


def test_confirm_booking_after_cancel_with_aligned_slot(monkeypatch):
    from app.services.interview_booking_service import (
        _filter_slots_to_calling_hours,
        _slot_starts,
        booking_window_bounds,
    )

    monkeypatch.setattr(
        "app.services.interview_booking_service.interview_relax_restrictions",
        lambda: True,
    )

    with get_sessionmaker()() as db:
        org, order, recipient, token = _seed_booking(db, booked=True)
        order.scheduled_end_at = datetime.utcnow() + timedelta(days=2)
        db.add(order)
        db.commit()
        InterviewBookingService.cancel_booking(db, token.token, source="whatsapp")
        db.refresh(token)
        assert token.booked_start_at is None
        now = datetime.utcnow()
        win_start, win_end = booking_window_bounds(order, now=now)
        slots = _filter_slots_to_calling_hours(db, order, _slot_starts(win_start, win_end, now=now))
        assert slots, "expected at least one bookable slot after cancel"
        slot_iso = slots[0].isoformat() + "Z"
        result = InterviewBookingService.confirm_booking(db, token.token, slot_iso)
        assert result.get("ok") is True
        db.refresh(token)
        assert token.booked_start_at is not None


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


def test_extract_telnyx_nested_button_reply():
    from app.services.telnyx_inbound_messaging_service import _extract_message_text, extract_wa_button_reply

    payload = {
        "type": "whatsapp",
        "whatsapp_message": {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "cancel", "title": "❌ Cancel"},
            },
        },
    }
    assert _extract_message_text(payload) == "❌ Cancel"
    assert extract_wa_button_reply(payload)["title"] == "❌ Cancel"

    telnyx_uuid_body = {
        "body": "db65f888-138e-4d9f-bbd3-0516a8acfc68",
        "type": "whatsapp",
        "whatsapp_message": {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {
                    "id": "db65f888-138e-4d9f-bbd3-0516a8acfc68",
                    "title": "❌ Cancel",
                },
            },
        },
    }
    assert _extract_message_text(telnyx_uuid_body) == "❌ Cancel"
    assert extract_wa_button_reply(telnyx_uuid_body)["id"] == "db65f888-138e-4d9f-bbd3-0516a8acfc68"

    nested = {
        "data": {
            "payload": {
                "whatsapp_message": {
                    "interactive": {"button_reply": {"title": "Cancel"}},
                }
            }
        }
    }
    from app.services.telnyx_inbound_messaging_service import _deep_wa_reply_text

    assert _deep_wa_reply_text(nested) == "Cancel"


def test_resolve_intent_from_template_button_id():
    import json
    import uuid

    from app.core.database import get_sessionmaker
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
    from app.services.interview_whatsapp_inbound_service import resolve_interview_booking_intent

    button_id = "db65f888-138e-4d9f-bbd3-0516a8acfc68"
    components = [
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "🔄 Reschedule", "id": "reschedule-id"},
                {"type": "QUICK_REPLY", "text": "❌ Cancel", "id": button_id},
            ],
        }
    ]
    with get_sessionmaker()() as db:
        db.add(
            TelnyxWhatsappTemplate(
                telnyx_record_id="rec-" + uuid.uuid4().hex[:8],
                template_id="tpl-" + uuid.uuid4().hex[:8],
                name="voxbulk_interview_confirm",
                language="en_US",
                status="APPROVED",
                components_json=json.dumps(components),
            )
        )
        db.commit()
        assert resolve_interview_booking_intent(db, body=button_id, button_id=button_id) == "cancel"
