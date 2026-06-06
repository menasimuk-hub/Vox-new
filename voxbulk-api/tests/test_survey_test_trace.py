"""Forensic trace + Start survey plain-text + session invalidation regression."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_runtime_service import (
    attach_builder_runtime_to_config,
    build_builder_runtime,
    reject_stale_graph_session,
)
from app.services.survey_session_service import SurveySessionService
from app.services.survey_wa_inbound_parse_service import (
    NormalizedWaInboundReply,
    detect_start_matcher,
)
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply


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


def test_detect_start_matcher_plain_text_start_survey():
    reply = NormalizedWaInboundReply(
        raw_text="Start survey",
        normalized_answer="Start survey",
    )
    action, matcher = detect_start_matcher(reply)
    assert action == "start_survey"
    assert matcher in {"plain_text_exact", "plain_text_fuzzy"}


def test_reject_stale_graph_session_does_not_kill_linear_awaiting_start(db):
    org = Organisation(name="Linear Session Org")
    db.add(org)
    db.commit()

    welcome = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome",
        display_name="welcome",
        language="en_US",
        category="MARKETING",
        body_preview="Hi",
        step_role="start",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Hi"}]),
    )
    q1 = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="q1",
        display_name="q1",
        language="en_US",
        category="MARKETING",
        body_preview="Rate",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Rate"}]),
    )
    db.add_all([welcome, q1])
    db.commit()

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
            "survey_test_trace_id": "st-test-linear-session",
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Trace test",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.add(order)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447954823445",
        status="sent",
        result_json=json.dumps(
            {
                "survey_test_trace_id": "st-test-linear-session",
                "wa_conversation": {
                    "step": 0,
                    "total": 1,
                    "intro_sent_at": datetime.utcnow().isoformat(),
                    "awaiting_start": True,
                },
            }
        ),
    )
    db.add(recipient)
    db.commit()

    session = SurveySessionService.ensure_awaiting_start_session(
        db,
        order=order,
        recipient=recipient,
        config=config,
    )
    assert session.flow_mode == "linear"
    assert session.flow_snapshot_json

    reject_stale_graph_session(
        db,
        recipient_id=recipient.id,
        order_id=order.id,
        runtime=runtime,
    )
    db.refresh(session)
    assert str(session.status).lower() == "active"
    assert SurveySessionService.get_active_by_recipient(db, recipient.id) is not None


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_start_survey_plain_text_sends_first_question(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Start Plain Org")
    db.add(org)
    db.commit()

    welcome = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome",
        display_name="welcome",
        language="en_US",
        category="MARKETING",
        body_preview="Hi",
        step_role="start",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Hi"}]),
    )
    q1 = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="rating",
        display_name="rating",
        language="en_US",
        category="MARKETING",
        body_preview="Rate",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Rate"}]),
    )
    db.add_all([welcome, q1])
    db.commit()

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
            "survey_test_trace_id": "st-plain-start",
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Plain start",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.add(order)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447954823445",
        status="sent",
        result_json=json.dumps(
            {
                "survey_test_trace_id": "st-plain-start",
                "wa_conversation": {
                    "step": 0,
                    "total": 1,
                    "intro_sent_at": datetime.utcnow().isoformat(),
                    "awaiting_start": True,
                },
            }
        ),
    )
    db.add(recipient)
    db.commit()
    SurveySessionService.ensure_awaiting_start_session(
        db,
        order=order,
        recipient=recipient,
        config=config,
    )

    result = handle_inbound_reply(
        db,
        from_phone="+447954823445",
        body="Start survey",
        org_id=org.id,
    )
    assert result.get("handled") is True
    assert result.get("started") is True
    assert result.get("next_template_id") == q1.id
    assert mock_send.called
