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


def test_send_invites_email_only_reports_missing_address(monkeypatch):
    with get_sessionmaker()() as db:
        order, _ = _seed_order_with_recipient(db, email_column=None, cv_email=None)
        monkeypatch.setattr(
            "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
            lambda *a, **k: None,
        )
        result = InterviewBookingService.send_invites(
            db, order, channels=["email"], force_email=True
        )
        assert result.get("email_sent") == 0
        assert result.get("ok") is False
        assert any("no email" in str(e).lower() for e in (result.get("errors") or []))


def test_send_invites_finds_email_in_cv_text(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(db, email_column=None, cv_email=None)
        recipient.cv_text = "Jane Doe\njane.candidate@example.com\n+447700900123"
        db.add(recipient)
        db.commit()
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
        assert send.call_args.kwargs.get("to_email") == "jane.candidate@example.com"
        db.refresh(recipient)
        assert recipient.email == "jane.candidate@example.com"


def test_send_interview_invitation_email_clears_stale_flags_on_force(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(
            db, email_column="alex@example.com", cv_email=None
        )
        recipient.result_json = json.dumps(
            {
                "invite_email_sent_at": "2026-01-01T00:00:00",
                "invite_email_ok": True,
                "invite_sent_to": "alex@example.com",
            }
        )
        db.add(recipient)
        db.commit()
        send = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send,
        )
        counted, merged, err = InterviewBookingService.send_interview_invitation_email(
            db,
            order=order,
            recipient=recipient,
            outreach_email="alex@example.com",
            role="Engineer",
            company_name="Acme",
            booking_url="https://example.com/book/token",
            force_email=True,
            smtp_ready=True,
        )
        assert err is None
        assert counted is True
        assert send.call_count == 1
        assert merged.get("invite_email_ok") is True
        assert merged.get("invitation_email_attempted_at")


def test_send_interview_invitation_email_skips_without_force_when_already_sent(monkeypatch):
    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(
            db, email_column="alex@example.com", cv_email=None
        )
        recipient.result_json = json.dumps(
            {
                "invite_email_sent_at": "2026-01-01T00:00:00",
                "invite_email_ok": True,
                "invite_sent_to": "alex@example.com",
            }
        )
        db.add(recipient)
        db.commit()
        send = MagicMock(return_value=(True, None))
        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            send,
        )
        counted, _merged, err = InterviewBookingService.send_interview_invitation_email(
            db,
            order=order,
            recipient=recipient,
            outreach_email="alex@example.com",
            role="Engineer",
            company_name="Acme",
            booking_url="https://example.com/book/token",
            force_email=False,
            smtp_ready=True,
        )
        assert err is None
        assert counted is True
        assert send.call_count == 0


def test_send_invites_continues_when_one_recipient_email_fails(monkeypatch):
    with get_sessionmaker()() as db:
        order, _ = _seed_order_with_recipient(db, email_column="good@example.com", cv_email=None)
        bad = ServiceOrderRecipient(
            order_id=order.id,
            row_number=2,
            name="Bad",
            phone="+447700900124",
            email="bad@example.com",
            status="pending",
        )
        db.add(bad)
        db.commit()

        def _send(db, *, template_key, to_email, variables, attachments=None):
            if to_email == "bad@example.com":
                return False, "smtp rejected"
            return True, None

        monkeypatch.setattr(
            "app.services.interview_booking_service.CareerEmailService.send_templated_critical",
            _send,
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
        assert result.get("ok") is True
        assert any("bad@example.com" in str(e) for e in (result.get("errors") or []))


def test_launch_endpoint_sends_email_via_shared_helper(app_client, monkeypatch):
    from app.core.security import hash_password
    from app.models.membership import OrganisationMembership
    from app.models.user import User

    with get_sessionmaker()() as db:
        org = Organisation(name="Launch API Org")
        db.add(org)
        db.flush()
        user = User(email=f"launch-api-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
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
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Alex",
                phone="+447700900123",
                email="alex@example.com",
                status="pending",
            )
        )
        db.commit()
        org_id = org.id
        order_id = order.id
        email = user.email

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    captured: dict[str, bool] = {}

    def _send_invites(db, order, **kwargs):
        captured["force_email"] = kwargs.get("force_email")
        captured["force_resend"] = kwargs.get("force_resend")
        return {"ok": True, "email_sent": 1, "whatsapp_sent": 1, "errors": []}

    monkeypatch.setattr(
        "app.services.interview_launch_service.InterviewBookingService.send_invites",
        _send_invites,
    )

    launched = app_client.post(
        f"/service-orders/{order_id}/interview/launch",
        headers=headers,
        json={"channels": ["email", "whatsapp"]},
    )
    assert launched.status_code == 200, launched.text
    body = launched.json()
    assert body.get("ok") is True
    assert captured.get("force_email") is True
    assert captured.get("force_resend") is True
