"""Booking invite email dispatch from launch/resend paths."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_booking_service import InterviewBookingService


@pytest.fixture(autouse=True)
def _ensure_sqlite_schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield


def _seed_order_with_recipient(db, *, email_column: str | None, cv_email: str | None):
    org = Organisation(name="Invite Org")
    db.add(org)
    db.flush()
    user = User(email=f"inv-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
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
        scheduled_end_at=now + timedelta(hours=4),
        config_json='{"delivery":"ai_call","role":"Engineer"}',
    )
    db.add(order)
    db.flush()
    cv_json = json.dumps({"email": cv_email}) if cv_email else None
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900123",
        email=email_column,
        cv_parsed_json=cv_json,
        status="pending",
    )
    db.add(recipient)
    db.commit()
    return order, recipient


def test_send_invites_uses_cv_parsed_email_when_column_empty(monkeypatch):
    with get_sessionmaker()() as db:
        order, _ = _seed_order_with_recipient(db, email_column=None, cv_email="alex@example.com")
        send = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send,
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
            MagicMock(),
        )
        monkeypatch.setattr(
            "app.services.telnyx_phone_allowlist_service.TelnyxPhoneAllowlistService.validate_phone_db",
            lambda *a, **k: {"allowed": True},
        )
        monkeypatch.setattr(
            "app.services.career_email_service.interview_email_delivery_status",
            lambda *a, **k: {"can_send_email": True, "smtp_configured": True, "smtp_enabled": True},
        )
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
            lambda *a, **k: None,
        )

        result = InterviewBookingService.send_invites(
            db, order, channels=["email"], force_email=True
        )
        assert result.get("email_sent") == 1
        assert send.call_args.kwargs.get("to_email") == "alex@example.com"
