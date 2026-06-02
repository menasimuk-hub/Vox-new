"""Stop/cancel interview emails must not silently drop when templates are disabled."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_booking_service import InterviewBookingService, SLOT_MINUTES


@pytest.fixture(autouse=True)
def _ensure_sqlite_schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield


def _seed_booked_candidate(db):
    org = Organisation(name="Stop Email Org")
    db.add(org)
    db.flush()
    user = User(
        email=f"stop-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    slot = datetime.utcnow() + timedelta(hours=2)
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        status="running",
        payment_status="approved",
        scheduled_start_at=datetime.utcnow(),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=6),
        config_json='{"role":"Engineer","delivery":"ai_call"}',
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="James",
        phone="+447700900123",
        email="james@example.com",
        status="pending",
    )
    db.add(recipient)
    db.flush()
    token = InterviewBookingToken(
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=org.id,
        token=f"tok-{uuid.uuid4().hex}",
        booked_start_at=slot,
        booked_end_at=slot + timedelta(minutes=SLOT_MINUTES),
    )
    db.add(token)
    db.commit()
    return order, recipient, slot


def test_booking_cancel_email_uses_critical_fallback(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient, slot = _seed_booked_candidate(db)
        send_plain = MagicMock()
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
            lambda *a, **k: (False, "template_disabled"),
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send",
            send_plain,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation_whatsapp",
            lambda *a, **k: False,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._hangup_active_call_if_any",
            lambda *a, **k: None,
        )

        token_row = db.execute(
            __import__("sqlalchemy").select(InterviewBookingToken).where(
                InterviewBookingToken.recipient_id == recipient.id
            )
        ).scalar_one()

        result = InterviewBookingService.cancel_booking(db, token=token_row.token, source="web")

        assert result.get("cancellation_email_sent") is True
        send_plain.assert_called_once()
        assert "interview" in str(send_plain.call_args.kwargs.get("subject") or "").lower() or "cancel" in str(
            send_plain.call_args.kwargs.get("subject") or ""
        ).lower()


def test_booking_cancel_email_falls_back_on_smtp_error(monkeypatch):
    """Broken admin template SMTP error must still send code-default cancel email."""
    with get_sessionmaker()() as db:
        order, recipient, slot = _seed_booked_candidate(db)
        send_plain = MagicMock()
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
            lambda *a, **k: (False, "SMTP connection refused"),
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send",
            send_plain,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation_whatsapp",
            lambda *a, **k: False,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._hangup_active_call_if_any",
            lambda *a, **k: None,
        )

        token_row = db.execute(
            __import__("sqlalchemy").select(InterviewBookingToken).where(
                InterviewBookingToken.recipient_id == recipient.id
            )
        ).scalar_one()

        result = InterviewBookingService.cancel_booking(db, token=token_row.token, source="web")

        assert result.get("cancellation_email_sent") is True
        send_plain.assert_called_once()


def test_stop_still_emails_invited_candidate_with_cancelled_status(monkeypatch):
    """Employer stop must email invited candidates even if status was already cancelled."""
    with get_sessionmaker()() as db:
        order, recipient, slot = _seed_booked_candidate(db)
        order.config_json = (
            '{"role":"Engineer","booking_invites_sent_at":"2026-01-01T00:00:00",'
            '"last_invite_dispatch":{"ok":true}}'
        )
        recipient.result_json = '{"invite_email_sent_at":"2026-01-01T00:00:00"}'
        recipient.status = "cancelled"
        db.add(order)
        db.add(recipient)
        db.commit()

        cancel_email = MagicMock(return_value=True)
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation",
            cancel_email,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation_whatsapp",
            lambda *a, **k: False,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._hangup_active_call_if_any",
            lambda *a, **k: None,
        )

        result = InterviewBookingService.notify_campaign_closed(db, order)
        assert result.get("email_sent") == 1
        cancel_email.assert_called_once()


def test_stop_order_sends_closure_email_synchronously(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient, slot = _seed_booked_candidate(db)
        order.config_json = (
            '{"role":"Engineer","booking_invites_sent_at":"2026-01-01T00:00:00",'
            '"last_invite_dispatch":{"ok":true,"whatsapp_sent":1,"email_sent":0}}'
        )
        recipient.result_json = json.dumps(
            {
                "invite_wa_sent_at": "2026-01-01T00:00:00",
                "booking_url": "https://dashboard.voxbulk.com/book/test",
            }
        )
        db.add(order)
        db.add(recipient)
        db.commit()

        cancel_email = MagicMock(return_value=True)
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation",
            cancel_email,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._send_booking_cancellation_whatsapp",
            lambda *a, **k: False,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService._hangup_active_call_if_any",
            lambda *a, **k: None,
        )

        from app.services.platform_catalog_service import ServiceOrderService

        ServiceOrderService.stop_order(db, order, reason="Stopped for testing")
        cancel_email.assert_called_once()
