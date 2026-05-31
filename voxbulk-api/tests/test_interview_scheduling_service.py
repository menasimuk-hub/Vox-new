"""Tests for human-interview scheduling send (Calendly/Cronofy stage B)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.models.user import User
from app.services.interview_scheduling_service import InterviewSchedulingService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.scheduling_connection_service import save_scheduling_config


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def interview_order_with_calendly(db_session: Session):
    org = Organisation(name="Scheduling Org")
    user = User(email=f"sched-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    save_scheduling_config(
        db_session,
        org.id,
        {
            "provider": "calendly",
            "access_token": "test-token",
            "event_type_uri": "https://api.calendly.com/event_types/abc",
            "owner_name": "Recruiter",
        },
    )
    order = ServiceOrderService.create_order(
        db_session,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer screening",
        config={"role": "Senior Engineer"},
    )
    db_session.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Alice Example",
            phone="+447700900001",
            email="alice@example.com",
            status="completed",
        )
    )
    db_session.commit()
    db_session.refresh(order)
    return order


def test_send_scheduling_requires_org_connection(db_session: Session):
    org = Organisation(name="No Calendar Org")
    user = User(email=f"nosched-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    order = ServiceOrderService.create_order(
        db_session,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Role",
        config={},
    )
    db_session.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Bob",
            phone="+447700900002",
            email="bob@example.com",
            status="completed",
        )
    )
    db_session.commit()
    db_session.refresh(order)
    recipient_id = ServiceOrderService.get_recipients(db_session, order.id)[0].id

    with pytest.raises(ValueError, match="Connect Calendly or Cronofy"):
        InterviewSchedulingService.send_scheduling_links(
            db_session,
            order,
            recipient_ids=[recipient_id],
        )


@patch("app.services.interview_scheduling_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.career_email_service.CareerEmailService.send_templated_optional")
@patch("app.services.interview_scheduling_service.create_scheduling_link")
@patch("app.services.interview_scheduling_service._resolve_scheduling_wa_template")
def test_send_scheduling_links_stores_url(
    mock_template,
    mock_create_link,
    mock_email,
    mock_wa,
    db_session: Session,
    interview_order_with_calendly,
):
    from app.services.telnyx_messaging_service import TelnyxMessageResult

    recipients = ServiceOrderService.get_recipients(db_session, interview_order_with_calendly.id)
    recipient_id = recipients[0].id

    mock_template.return_value = type(
        "Row",
        (),
        {
            "name": "voxbulk_sched",
            "language": "en_US",
            "sales_template_key": None,
            "components_json": "null",
            "telnyx_record_id": "tmpl-test-1",
        },
    )()
    mock_create_link.return_value = "https://calendly.com/acme/interview/abc123"
    mock_email.return_value = (True, None)
    mock_wa.return_value = TelnyxMessageResult(ok=True, status="sent", channel="whatsapp")

    result = InterviewSchedulingService.send_scheduling_links(
        db_session,
        interview_order_with_calendly,
        recipient_ids=[recipient_id],
        channels=["whatsapp", "email"],
    )

    assert result["ok"] is True
    assert result["whatsapp_sent"] == 0
    assert result["email_sent"] == 1
    assert result["provider"] == "calendly"
    mock_create_link.assert_called_once()

    db_session.refresh(recipients[0])
    parsed = json.loads(recipients[0].result_json or "{}")
    assert parsed["scheduling_url"] == "https://calendly.com/acme/interview/abc123"
    assert parsed.get("scheduling_url_sent_at")
