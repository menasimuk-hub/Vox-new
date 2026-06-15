"""Campaign closure: email all invited candidates; WhatsApp only if they booked."""

from __future__ import annotations

import json
import time
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
from app.services.interview_booking_service import (
    InterviewBookingService,
    SLOT_MINUTES,
    campaign_invites_were_sent,
    recipient_received_booking_outreach,
)


@pytest.fixture(autouse=True)
def _ensure_sqlite_schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield


def _seed_draft_with_recipient(db):
    org = Organisation(name="Notify Org")
    db.add(org)
    db.flush()
    user = User(email=f"notify-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Interview draft",
        status="draft",
        payment_status="unpaid",
        config_json='{"role":"Engineer","position":"Engineer"}',
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
    db.commit()
    return order, recipient


def test_campaign_invites_were_sent_false_for_saved_draft():
    with get_sessionmaker()() as db:
        order, _ = _seed_draft_with_recipient(db)
        assert campaign_invites_were_sent(order) is False


def test_notify_campaign_closed_skips_unlaunched_draft(monkeypatch):
    with get_sessionmaker()() as db:
        order, _ = _seed_draft_with_recipient(db)
        send_wa = MagicMock()
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
            send_wa,
        )
        result = InterviewBookingService.notify_campaign_closed(db, order)
        assert result.get("skipped") is True
        assert result.get("reason") == "invites_never_sent"
        send_wa.assert_not_called()


def test_delete_order_does_not_notify_unlaunched_draft(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        notify = MagicMock()
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService.notify_campaign_closed",
            notify,
        )
        from app.services.platform_catalog_service import ServiceOrderService

        ServiceOrderService.delete_order(db, order)
        notify.assert_not_called()
        db.refresh(order)
        assert order.status == "archived"
        assert db.get(ServiceOrderRecipient, recipient.id) is not None


def test_recipient_received_booking_outreach_requires_invite_or_booking():
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        token = InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=order.org_id,
            token=f"tok-{uuid.uuid4().hex}",
        )
        db.add(token)
        db.commit()
        assert recipient_received_booking_outreach(recipient, token) is False

        token.wa_sent_at = datetime.utcnow()
        assert recipient_received_booking_outreach(recipient, token) is True


def test_notify_email_only_when_invited_not_booked(monkeypatch):
    """Invite sent but no slot booked → email yes, WhatsApp no (WA costs money)."""
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        order.config_json = json.dumps(
            {
                "role": "IT role 04",
                "position": "IT role 04",
                "booking_invites_sent_at": datetime.utcnow().isoformat(),
                "last_invite_dispatch": {"ok": True},
            }
        )
        recipient.result_json = json.dumps({"invite_email_sent_at": datetime.utcnow().isoformat()})
        token = InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=order.org_id,
            token=f"tok-{uuid.uuid4().hex}",
            wa_sent_at=datetime.utcnow(),
        )
        db.add(order)
        db.add(recipient)
        db.add(token)
        db.commit()

        send_wa = MagicMock()
        send_wa.return_value = MagicMock(ok=True, message_id="msg-1")
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
            send_wa,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
            lambda *a, **k: (True, None),
        )

        result = InterviewBookingService.notify_campaign_closed(db, order)
        assert result.get("email_sent") == 1
        assert result.get("whatsapp_sent") == 0
        send_wa.assert_not_called()


def test_notify_email_both_wa_only_booked(monkeypatch):
    """Two candidates: email both, WhatsApp only the one who booked a slot."""
    with get_sessionmaker()() as db:
        org = Organisation(name="Close Org")
        db.add(org)
        db.flush()
        user = User(email=f"close-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="interview",
            title="IT role 04",
            status="running",
            payment_status="approved",
            config_json=json.dumps(
                {
                    "role": "IT role 04",
                    "booking_invites_sent_at": datetime.utcnow().isoformat(),
                    "last_invite_dispatch": {"ok": True},
                }
            ),
        )
        db.add(order)
        db.flush()

        booked = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="James",
            phone="+447700900111",
            email="james@example.com",
            status="pending",
            result_json=json.dumps({"invite_email_sent_at": datetime.utcnow().isoformat()}),
        )
        not_booked = ServiceOrderRecipient(
            order_id=order.id,
            row_number=2,
            name="Daddy",
            phone="+447700900222",
            email="daddy@example.com",
            status="pending",
            result_json=json.dumps({"invite_email_sent_at": datetime.utcnow().isoformat()}),
        )
        db.add(booked)
        db.add(not_booked)
        db.flush()

        slot = datetime.utcnow() + timedelta(days=1)
        db.add(
            InterviewBookingToken(
                order_id=order.id,
                recipient_id=booked.id,
                org_id=org.id,
                token=f"tok-booked-{uuid.uuid4().hex[:8]}",
                booked_start_at=slot,
                booked_end_at=slot + timedelta(minutes=SLOT_MINUTES),
                wa_sent_at=datetime.utcnow(),
            )
        )
        db.add(
            InterviewBookingToken(
                order_id=order.id,
                recipient_id=not_booked.id,
                org_id=org.id,
                token=f"tok-open-{uuid.uuid4().hex[:8]}",
                wa_sent_at=datetime.utcnow(),
            )
        )
        db.commit()

        send_wa = MagicMock()
        send_wa.return_value = MagicMock(ok=True, message_id="msg-wa")
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
            send_wa,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_optional",
            lambda *a, **k: (True, None),
        )

        result = InterviewBookingService.notify_campaign_closed(db, order)
        assert result.get("email_sent") == 2
        assert result.get("whatsapp_sent") == 1
        assert send_wa.call_count == 1
        assert send_wa.call_args.kwargs.get("to_number") == "+447700900111"


def test_send_invites_rejected_when_campaign_stopped():
    with get_sessionmaker()() as db:
        order, _ = _seed_draft_with_recipient(db)
        order.status = "cancelled"
        order.payment_status = "approved"
        order.scheduled_start_at = datetime.utcnow() + timedelta(days=1)
        order.scheduled_end_at = datetime.utcnow() + timedelta(days=2)
        order.config_json = json.dumps(
            {
                "role": "Engineer",
                "booking_invites_sent_at": datetime.utcnow().isoformat(),
                "last_invite_dispatch": {"ok": True},
            }
        )
        db.add(order)
        db.commit()

        with pytest.raises(ValueError, match="stopped"):
            InterviewBookingService.send_invites(db, order, force_resend=True)


def test_send_invites_rejected_when_campaign_finished():
    with get_sessionmaker()() as db:
        order, _ = _seed_draft_with_recipient(db)
        order.status = "completed"
        order.payment_status = "approved"
        order.scheduled_start_at = datetime.utcnow() - timedelta(days=2)
        order.scheduled_end_at = datetime.utcnow() - timedelta(days=1)
        db.add(order)
        db.commit()

        with pytest.raises(ValueError, match="finished"):
            InterviewBookingService.send_invites(db, order, force_resend=True)


def test_stop_order_notifies_pending_booked_candidate_before_cancelling(monkeypatch):
    """Employer stop must email + WhatsApp booked candidates still marked pending."""
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        order.status = "running"
        order.payment_status = "approved"
        order.scheduled_start_at = datetime.utcnow()
        order.scheduled_end_at = datetime.utcnow() + timedelta(hours=4)
        order.config_json = json.dumps(
            {
                "role": "Engineer",
                "booking_invites_sent_at": datetime.utcnow().isoformat(),
                "last_invite_dispatch": {"ok": True},
            }
        )
        recipient.result_json = json.dumps({"invite_email_sent_at": datetime.utcnow().isoformat()})
        slot = datetime.utcnow() + timedelta(hours=1)
        db.add(order)
        db.add(recipient)
        db.flush()
        db.add(
            InterviewBookingToken(
                order_id=order.id,
                recipient_id=recipient.id,
                org_id=order.org_id,
                token=f"tok-stop-{uuid.uuid4().hex[:8]}",
                booked_start_at=slot,
                booked_end_at=slot + timedelta(minutes=SLOT_MINUTES),
                wa_sent_at=datetime.utcnow(),
            )
        )
        db.commit()

        send_wa = MagicMock()
        send_wa.return_value = MagicMock(ok=True, message_id="msg-stop")
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
            send_wa,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
            lambda *a, **k: None,
        )
        email_calls: list[str] = []

        def _capture_critical(db, *, template_key, to_email, variables, attachments=None):
            email_calls.append(template_key)
            return True, None

        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            _capture_critical,
        )

        from app.services.platform_catalog_service import ServiceOrderService

        ServiceOrderService.stop_order(db, order, reason="Stopped for testing")

        assert email_calls and email_calls[0] in {
            "interview_campaign_cancelled",
            "interview_booking_cancel",
        }
        assert send_wa.call_count == 1

        for _ in range(100):
            db.refresh(recipient)
            if str(recipient.status or "").lower() == "cancelled":
                break
            time.sleep(0.02)

        assert str(recipient.status or "").lower() == "cancelled"


def test_notify_campaign_closed_sends_closure_email_via_critical_template(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        order.status = "running"
        order.payment_status = "approved"
        order.config_json = json.dumps(
            {
                "role": "Engineer",
                "booking_invites_sent_at": datetime.utcnow().isoformat(),
                "last_invite_dispatch": {"ok": True},
            }
        )
        recipient.result_json = json.dumps({"invite_email_sent_at": datetime.utcnow().isoformat()})
        db.add(order)
        db.add(recipient)
        db.flush()
        db.add(
            InterviewBookingToken(
                order_id=order.id,
                recipient_id=recipient.id,
                org_id=order.org_id,
                token=f"tok-email-{uuid.uuid4().hex[:8]}",
                wa_sent_at=datetime.utcnow(),
            )
        )
        db.commit()

        send_critical = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send_critical,
        )

        result = InterviewBookingService.notify_campaign_closed(db, order)
        assert result.get("email_sent") == 1
        send_critical.assert_called_once()


def test_notify_campaign_closed_emails_uninvited_when_requested(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        send_critical = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send_critical,
        )
        result = InterviewBookingService.notify_campaign_closed(
            db, order, reason="Stopped before launch", include_uninvited=True
        )
        assert result.get("email_sent") == 1
        send_critical.assert_called_once()


def test_stop_order_notifies_candidates_even_when_invites_never_sent(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        order.status = "paid"
        order.payment_status = "approved"
        order.scheduled_start_at = datetime.utcnow()
        order.scheduled_end_at = datetime.utcnow() + timedelta(hours=4)
        db.add(order)
        db.commit()

        send_critical = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send_critical,
        )
        from app.services.platform_catalog_service import ServiceOrderService

        ServiceOrderService.stop_order(db, order, reason="Stopped for testing")
        send_critical.assert_called_once()
        args, kwargs = send_critical.call_args
        assert kwargs.get("to_email") == "james@example.com"
