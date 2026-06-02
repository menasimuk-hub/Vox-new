"""Booking confirmation email after candidate picks a slot."""

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
from app.services.interview_booking_service import InterviewBookingService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    yield


def _seed(db):
    org = Organisation(name="Confirm Org")
    db.add(org)
    db.flush()
    user = User(email=f"c-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    now = datetime.utcnow()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        status="paid",
        payment_status="approved",
        scheduled_start_at=now,
        scheduled_end_at=now + timedelta(hours=8),
        config_json='{"delivery":"ai_call","role":"Engineer"}',
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900123",
        email=None,
        cv_parsed_json=json.dumps({"email": "alex@example.com"}),
        status="pending",
    )
    db.add(recipient)
    db.flush()
    token = InterviewBookingToken(
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=org.id,
        token="confirm-" + uuid.uuid4().hex,
    )
    db.add(token)
    db.commit()
    return order, recipient, token


def test_send_booking_confirmations_uses_cv_email(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient, _ = _seed(db)
        send = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send,
        )
        monkeypatch.setattr(
            "app.services.career_email_service.interview_email_delivery_status",
            lambda *a, **k: {"can_send_email": True},
        )
        slot = datetime.utcnow() + timedelta(days=1, hours=2)
        result = InterviewBookingService._send_booking_confirmations(db, order, recipient, slot)
        assert result["confirmation_email_sent"] is True
        assert send.call_args.kwargs["to_email"] == "alex@example.com"
        db.refresh(recipient)
        assert recipient.email == "alex@example.com"


def test_confirmation_fallback_on_template_failure(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient, _ = _seed(db)
        recipient.email = "alex@example.com"
        db.add(recipient)
        db.commit()
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            lambda *a, **k: (False, "html_rejected"),
        )
        fallback = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_booking_confirmation_fallback",
            fallback,
        )
        monkeypatch.setattr(
            "app.services.career_email_service.interview_email_delivery_status",
            lambda *a, **k: {"can_send_email": True},
        )
        slot = datetime.utcnow() + timedelta(days=1, hours=2)
        result = InterviewBookingService._send_booking_confirmations(db, order, recipient, slot)
        assert result["confirmation_email_sent"] is True
        fallback.assert_called_once()
