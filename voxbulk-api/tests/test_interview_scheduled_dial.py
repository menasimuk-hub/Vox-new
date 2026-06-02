"""Booked (scheduled) recipients must be dialed at slot time."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_call_dispatch_service import InterviewCallDispatchService, VOICE_DIALABLE
from app.services.platform_catalog_service import PlatformCatalogService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def test_sent_recipient_is_dialable():
    assert "sent" in VOICE_DIALABLE


def test_dial_next_recipient_picks_scheduled_booked_candidate(db, monkeypatch):
    now = datetime.utcnow()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="interview",
        status="running",
        title="E2E",
        payment_status="approved",
        recipient_count=1,
        scheduled_start_at=now - timedelta(minutes=30),
        scheduled_end_at=now + timedelta(hours=4),
        config_json=json.dumps({"require_booking": True, "delivery": "ai_call", "script_approved": True}),
    )
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Test Candidate",
        phone="+447954823445",
        email="test@example.com",
        status="scheduled",
        result_json="{}",
    )
    token = InterviewBookingToken(
        id=str(uuid.uuid4()),
        order_id=order.id,
        recipient_id=recipient.id,
        org_id=order.org_id,
        token="test-token",
        booked_start_at=now - timedelta(minutes=1),
        booked_end_at=now + timedelta(minutes=1),
    )
    db.add(order)
    db.add(recipient)
    db.add(token)
    db.commit()

    monkeypatch.setattr(
        "app.services.interview_voice_agent_service.resolve_interview_telnyx_assistant_id",
        lambda *_a, **_k: ("assistant-test", MagicMock(id="agent-1")),
    )
    monkeypatch.setattr(
        "app.services.interview_call_dispatch_service._order_window_ok",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "app.services.interview_call_dispatch_service._any_recipient_calling",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.services.interview_voice_agent_service.should_skip_recipient_for_opt_out",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.services.interview_voice_agent_service.should_wait_for_retry",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.services.org_opt_out_service.OrgOptOutService.is_phone_opted_out",
        lambda *_a, **_k: False,
    )

    dialed: list[str] = []

    def _fake_dial(db, order, recipient, *, agent, assistant_id):
        dialed.append(recipient.id)
        recipient.status = "calling"
        db.add(recipient)
        db.commit()
        return recipient

    monkeypatch.setattr(
        InterviewCallDispatchService,
        "_dial_recipient",
        staticmethod(_fake_dial),
    )

    row = InterviewCallDispatchService.dial_next_recipient(db, order)
    assert row is not None
    assert row.id == recipient.id
    assert dialed == [recipient.id]
