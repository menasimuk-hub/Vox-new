"""Step 5 WA test must persist active session before welcome; inbound must match it."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_runtime_service import attach_builder_runtime_to_config, build_builder_runtime
from app.services.survey_builder_test_service import SurveyBuilderTestService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_whatsapp_conversation_service import (
    find_active_recipient_for_inbound,
    handle_inbound_reply,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        yield session
    finally:
        session.close()


def _tpl(db, *, name: str, body: str, step_role: str):
    record_id = str(uuid.uuid4())
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id,
        name=name,
        display_name=name,
        language="en_US",
        category="MARKETING",
        body_preview=body,
        step_role=step_role,
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": body}]),
    )
    db.add(row)
    db.commit()
    return row


def _seed_order(db, org_id: str):
    welcome = _tpl(db, name="welcome", body="Hi {{1}}", step_role="start")
    q1 = _tpl(db, name="q1", body="Rate {{1}}", step_role="rating")
    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[q1.id],
    )
    config = attach_builder_runtime_to_config(
        {
            "delivery": "whatsapp",
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "wa_template_id": welcome.id,
            "wa_builder_test": True,
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id="user-1",
        service_code="survey",
        title="WA Builder Test",
        status="draft",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.add(order)
    db.commit()
    return order, q1, org_id


@pytest.fixture()
def org(db):
    org = Organisation(name="Session Lifecycle Org")
    db.add(org)
    db.commit()
    return org


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_step5_send_test_creates_active_session(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, _q1, org_id = _seed_order(db, org.id)

    result = SurveyBuilderTestService.start_wa_test_session(
        db,
        org_id=org_id,
        user_id="user-1",
        order_id=order.id,
        test_phone="+447954823445",
    )

    assert result["session_id"] is not None
    session = SurveySessionService.get_active_by_recipient(db, result["recipient_id"])
    assert session is not None
    assert session.id == result["session_id"]
    assert str(session.status).lower() == "active"
    assert int(session.current_step or 0) == 0

    order_found, recipient, via = find_active_recipient_for_inbound(
        db,
        from_phone="+447954823445",
        org_id=org_id,
    )
    assert order_found is not None
    assert recipient is not None
    assert via in {"org_recipient", "session_phone", "session_phone_cross_org"}


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_step5_start_inbound_sends_first_template(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, q1, org_id = _seed_order(db, org.id)

    SurveyBuilderTestService.start_wa_test_session(
        db,
        org_id=org_id,
        user_id="user-1",
        order_id=order.id,
        test_phone="+447954823445",
    )

    result = handle_inbound_reply(
        db,
        from_phone="+447954823445",
        body="Start survey",
        org_id=org_id,
    )
    assert result.get("handled") is True
    assert result.get("started") is True
    assert result.get("next_template_id") == q1.id
    assert mock_send.call_count >= 2


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_step5_fast_inbound_after_welcome(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, q1, org_id = _seed_order(db, org.id)

    start = SurveyBuilderTestService.start_wa_test_session(
        db,
        org_id=org_id,
        user_id="user-1",
        order_id=order.id,
        test_phone="+447954823445",
    )

    session = SurveySessionService.get_active_by_recipient(db, start["recipient_id"])
    assert session is not None

    result = handle_inbound_reply(
        db,
        from_phone="+447954823445",
        body="Start",
        org_id=org_id,
    )
    assert result.get("handled") is True
    assert result.get("next_template_id") == q1.id
