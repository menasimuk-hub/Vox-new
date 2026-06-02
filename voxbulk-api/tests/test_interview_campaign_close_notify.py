"""Campaign closure notifications must not fire for unlaunched drafts."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_booking_service import (
    InterviewBookingService,
    campaign_invites_were_sent,
    recipient_received_booking_outreach,
)
from app.services.platform_catalog_service import ServiceOrderService


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
        ServiceOrderService.delete_order(db, order)
        notify.assert_not_called()
        assert db.get(ServiceOrderRecipient, recipient.id) is None


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


def test_notify_only_contacted_recipients_after_launch(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_draft_with_recipient(db)
        order.config_json = json.dumps(
            {
                "role": "IT role 03",
                "position": "IT role 03",
                "booking_invites_sent_at": datetime.utcnow().isoformat(),
                "last_invite_dispatch": {"ok": True},
            }
        )
        recipient.result_json = json.dumps({"invite_wa_sent_at": datetime.utcnow().isoformat()})
        db.add(order)
        db.add(recipient)
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
        assert result.get("skipped") == 0
        assert send_wa.call_count == 1
