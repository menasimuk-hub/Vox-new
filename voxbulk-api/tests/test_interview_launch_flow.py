"""Interview launch and slot-based dial eligibility."""

from __future__ import annotations

from datetime import datetime, timedelta
import uuid

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_booking_service import SLOT_MINUTES
from app.services.interview_call_dispatch_service import _recipient_eligible_for_dial
from app.services.interview_launch_service import InterviewLaunchService
from app.services.uk_compliance_opt_out import should_block_outbound_phone


def _seed_interview(db, *, phone="+447700900123", email="alex@example.com"):
    org = Organisation(name="Launch Org")
    db.add(org)
    db.flush()
    user = User(email=f"launch-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    now = datetime.utcnow()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        status="quoted",
        payment_status="approved",
        scheduled_start_at=now,
        scheduled_end_at=now + timedelta(hours=4),
        config_json='{"delivery":"ai_call","role":"Engineer","script_approved":true,"approved_script":"Hello"}',
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone=phone,
        email=email,
        status="pending",
    )
    db.add(recipient)
    db.flush()
    token = InterviewBookingToken(
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=org.id,
        token="test-token-" + uuid.uuid4().hex,
    )
    db.add(token)
    db.commit()
    return org, order, recipient, token


def test_launch_after_payment_schedules_without_immediate_dial(monkeypatch):
    with get_sessionmaker()() as db:
        _, order, _, _ = _seed_interview(db)
        sent = {"ok": True, "whatsapp_sent": 1, "email_sent": 1, "errors": []}

        monkeypatch.setattr(
            "app.services.interview_launch_service.InterviewBookingService.send_invites",
            lambda *a, **k: sent,
        )

        result = InterviewLaunchService.launch_after_payment(db, order)
        db.refresh(order)

        assert result["ok"] is True
        assert result.get("already_launched") is True
        assert order.status in {"scheduled", "paid"}
        assert result.get("invites") is not None
        cfg = __import__("json").loads(order.config_json or "{}")
        assert cfg.get("require_booking") is True


def test_launch_after_payment_does_not_schedule_when_email_not_sent(monkeypatch):
    with get_sessionmaker()() as db:
        _, order, _, _ = _seed_interview(db)
        prior_status = order.status
        sent = {"ok": False, "whatsapp_sent": 1, "email_sent": 0, "errors": ["SMTP disabled"]}

        monkeypatch.setattr(
            "app.services.interview_launch_service.InterviewBookingService.send_invites",
            lambda *a, **k: sent,
        )

        result = InterviewLaunchService.launch_after_payment(db, order)
        db.refresh(order)
        assert result["ok"] is False
        assert result.get("already_launched") is True
        assert int((result.get("invites") or {}).get("email_sent") or 0) == 0
        assert int((result.get("invites") or {}).get("whatsapp_sent") or 0) == 1
        # schedule_order must not run when email contract fails
        assert order.status == prior_status


def test_launch_rejects_invalid_phone_before_send(monkeypatch):
    with get_sessionmaker()() as db:
        _, order, recipient, _ = _seed_interview(db)
        recipient.phone = "12"
        db.add(recipient)
        db.commit()

        called = {"n": 0}

        def _boom(*a, **k):
            called["n"] += 1
            return {"ok": True, "whatsapp_sent": 1, "email_sent": 1, "errors": []}

        monkeypatch.setattr(
            "app.services.interview_launch_service.InterviewBookingService.send_invites",
            _boom,
        )

        with pytest.raises(ValueError, match="invalid candidate phone|E.164"):
            InterviewLaunchService.launch_after_payment(db, order)
        assert called["n"] == 0


def test_should_block_outbound_phone_invalid_does_not_raise():
    with get_sessionmaker()() as db:
        org = Organisation(name="OptOut Org")
        db.add(org)
        db.commit()
        reason = should_block_outbound_phone(db, org_id=org.id, phone_e164="not-a-phone")
        assert reason == "invalid_phone"


def test_dial_eligible_only_when_booked_slot_due():
    with get_sessionmaker()() as db:
        _, order, recipient, token = _seed_interview(db)
        now = datetime.utcnow()

        token.booked_start_at = now + timedelta(minutes=SLOT_MINUTES)
        db.add(token)
        db.commit()

        ok, reason = _recipient_eligible_for_dial(
            db, order, recipient, now=now, booking_required=True
        )
        assert ok is False
        assert reason == "slot_not_due"

        token.booked_start_at = now - timedelta(minutes=5)
        db.add(token)
        db.commit()

        ok, reason = _recipient_eligible_for_dial(
            db, order, recipient, now=now, booking_required=True
        )
        assert ok is True
        assert reason is None


def test_dial_skips_unbooked_candidate():
    with get_sessionmaker()() as db:
        _, order, recipient, token = _seed_interview(db)
        token.booked_start_at = None
        db.add(token)
        db.commit()

        ok, reason = _recipient_eligible_for_dial(
            db,
            order,
            recipient,
            now=datetime.utcnow(),
            booking_required=True,
        )
        assert ok is False
        assert reason == "not_booked"
