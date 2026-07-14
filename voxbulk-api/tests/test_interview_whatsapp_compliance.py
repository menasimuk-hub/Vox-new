"""UK outbound phone compliance helper boundaries — interview WhatsApp invite path."""

from __future__ import annotations

import inspect
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_booking_service import InterviewBookingService
from app.services.uk_compliance_opt_out import should_block_outbound_phone


@pytest.fixture(autouse=True)
def _ensure_sqlite_schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield


def _seed_order_with_recipient(db):
    org = Organisation(name="WA Compliance Org")
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
        status="paid",
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
        name="Alex",
        phone="+447700900123",
        email="alex@example.com",
        status="pending",
    )
    db.add(recipient)
    db.commit()
    return order, recipient


def _wa_template():
    return SimpleNamespace(
        name="interview_email_sent",
        language="en_US",
        id="tpl-1",
        telnyx_record_id="rec-1",
        body="Hello {{1}}",
        header=None,
        footer=None,
        buttons_json=json.dumps([]),
    )


def test_should_block_outbound_phone_signature_rejects_meter_usage():
    params = inspect.signature(should_block_outbound_phone).parameters
    assert "meter_usage" not in params
    assert set(params.keys()) == {"db", "org_id", "phone_e164"}


def test_should_block_outbound_phone_meter_usage_kwarg_raises():
    with get_sessionmaker()() as db:
        org = Organisation(name="Sig Org")
        db.add(org)
        db.commit()
        with pytest.raises(TypeError, match="meter_usage"):
            should_block_outbound_phone(db, org_id=org.id, phone_e164="+447700900123", meter_usage=False)


def test_interview_send_invites_whatsapp_compliance_helper_called_with_valid_args(monkeypatch):
    compliance_calls: list[dict] = []

    def _capture_block(db, *, org_id, phone_e164):
        compliance_calls.append({"org_id": org_id, "phone_e164": phone_e164})
        return None

    monkeypatch.setattr(
        "app.services.uk_compliance_opt_out.should_block_outbound_phone",
        _capture_block,
    )
    send_tpl = MagicMock(return_value=SimpleNamespace(ok=True, external_id="msg-1", status="sent", detail=None))
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.InterviewWhatsappSendService.send_template_or_plain",
        send_tpl,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
        MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
        lambda *a, **k: _wa_template(),
    )
    monkeypatch.setattr(
        "app.services.uk_compliance_service.UkComplianceService.assert_order_launch_allowed",
        lambda *a, **k: None,
    )

    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(db)
        result = InterviewBookingService.send_invites(db, order, channels=["whatsapp"])
        assert result.get("whatsapp_sent") == 1
        assert len(compliance_calls) == 1
        assert compliance_calls[0]["org_id"] == order.org_id
        assert compliance_calls[0]["phone_e164"] == recipient.phone


def test_interview_send_invites_whatsapp_respects_opt_out_without_sending(monkeypatch):
    monkeypatch.setattr(
        "app.services.uk_compliance_opt_out.should_block_outbound_phone",
        lambda *a, **k: "org_opt_out",
    )
    send_wa = MagicMock()
    monkeypatch.setattr(
        "app.services.interview_booking_service.TelnyxMessagingService.send_whatsapp",
        send_wa,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
        lambda *a, **k: _wa_template(),
    )
    monkeypatch.setattr(
        "app.services.uk_compliance_service.UkComplianceService.assert_order_launch_allowed",
        lambda *a, **k: None,
    )

    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(db)
        result = InterviewBookingService.send_invites(db, order, channels=["whatsapp"])
        assert result.get("whatsapp_sent") == 0
        send_wa.assert_not_called()
        assert any("org_opt_out" in str(e) for e in (result.get("errors") or []))


def test_interview_send_invites_whatsapp_send_preserves_meter_usage_false(monkeypatch):
    monkeypatch.setattr(
        "app.services.uk_compliance_opt_out.should_block_outbound_phone",
        lambda *a, **k: None,
    )
    send_wa = MagicMock(return_value=SimpleNamespace(ok=True, external_id="msg-2", status="sent", detail=None))
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.TelnyxMessagingService.send_whatsapp",
        send_wa,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
        MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
        lambda *a, **k: _wa_template(),
    )
    monkeypatch.setattr(
        "app.services.uk_compliance_service.UkComplianceService.assert_order_launch_allowed",
        lambda *a, **k: None,
    )

    with get_sessionmaker()() as db:
        order, _ = _seed_order_with_recipient(db)
        InterviewBookingService.send_invites(db, order, channels=["whatsapp"])
        assert send_wa.call_args.kwargs.get("meter_usage") is False


def test_interview_send_invites_whatsapp_ignores_call_allowlist(monkeypatch):
    """Call allowlist must not skip WA — destination policy is WhatsApp blocklist only."""
    monkeypatch.setattr(
        "app.services.uk_compliance_opt_out.should_block_outbound_phone",
        lambda *a, **k: None,
    )
    send_tpl = MagicMock(return_value=SimpleNamespace(ok=True, external_id="msg-wa", status="sent", detail=None))
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.InterviewWhatsappSendService.send_template_or_plain",
        send_tpl,
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.TelnyxMessagingService.log_outbound",
        MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.telnyx_phone_allowlist_service.TelnyxPhoneAllowlistService.validate_phone_db",
        lambda *a, **k: {"allowed": False, "reason": "EG calling is disabled"},
    )
    monkeypatch.setattr(
        "app.services.interview_booking_service.InterviewBookingService.resolve_invite_wa_template",
        lambda *a, **k: _wa_template(),
    )
    monkeypatch.setattr(
        "app.services.uk_compliance_service.UkComplianceService.assert_order_launch_allowed",
        lambda *a, **k: None,
    )

    with get_sessionmaker()() as db:
        order, recipient = _seed_order_with_recipient(db)
        recipient.phone = "+201012345678"
        db.add(recipient)
        db.commit()
        result = InterviewBookingService.send_invites(db, order, channels=["whatsapp"])
        assert result.get("whatsapp_sent") == 1
        send_tpl.assert_called_once()
        assert not any("allow" in str(e).lower() for e in (result.get("errors") or []))


def test_survey_dispatch_compliance_helper_has_no_meter_usage():
    import app.services.survey_dispatch_service as dispatch_module

    source = inspect.getsource(dispatch_module.SurveyDispatchService._dispatch_one)
    assert "should_block_outbound_phone(" in source
    assert "meter_usage" not in source.split("should_block_outbound_phone(")[1].split(")")[0]
