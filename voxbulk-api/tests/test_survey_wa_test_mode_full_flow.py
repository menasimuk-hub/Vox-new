"""Send test to my number must run the full builder workflow (same engine as live)."""

from __future__ import annotations

import json
import logging
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
from app.services.survey_dispatch_service import SurveyDispatchService
from app.services.survey_session_service import SurveySessionService
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


def _seed_multi_step_order(db, org_id: str):
    welcome = _tpl(db, name="welcome", body="Hi {{1}}", step_role="start")
    rating = _tpl(db, name="rating", body="Rate {{1}}", step_role="rating")
    follow = _tpl(db, name="follow", body="Recommend {{1}}?", step_role="yes_no")
    tell = _tpl(db, name="tell_us_more", body="Tell us more {{1}}", step_role="reason")
    thank = _tpl(db, name="thank_you", body="Thanks {{1}}", step_role="completion")
    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[rating.id, follow.id],
        tell_us_more_template_id=tell.id,
        thank_you_template_id=thank.id,
    )
    config = attach_builder_runtime_to_config(
        {
            "delivery": "whatsapp",
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "wa_template_id": welcome.id,
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id="user-1",
        service_code="survey",
        title="WA Builder Full Flow",
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
    return order, welcome, rating, follow, tell, thank, org_id


@pytest.fixture()
def org(db):
    org = Organisation(name="Full Flow Org")
    db.add(org)
    db.commit()
    return org


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_step5_full_workflow_logs_and_completes(mock_send, db, org, caplog):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, _welcome, rating, follow, tell, thank, org_id = _seed_multi_step_order(db, org.id)
    phone = "+447954823445"

    with caplog.at_level(logging.INFO):
        start = SurveyBuilderTestService.start_wa_test_session(
            db,
            org_id=org_id,
            user_id="user-1",
            order_id=order.id,
            test_phone=phone,
        )

    assert start["session_id"]
    phases = [rec.message for rec in caplog.records if "wa_test_mode_" in rec.message]
    assert any("wa_test_mode_started" in msg for msg in phases)
    assert any("wa_test_mode_session_created" in msg for msg in phases)
    assert any("wa_test_mode_welcome_sent" in msg for msg in phases)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        start_reply = handle_inbound_reply(db, from_phone=phone, body="Start", org_id=org_id)
    assert start_reply.get("started") is True
    assert start_reply.get("next_template_id") == rating.id
    assert any("wa_test_mode_start_transition" in rec.message for rec in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        low_rating = handle_inbound_reply(db, from_phone=phone, body="2", org_id=org_id)
    assert low_rating.get("handled") is True
    assert low_rating.get("payload_source") == "builder_tell_us_more_template"
    assert any("wa_test_mode_branch_taken" in rec.message for rec in caplog.records)
    assert any("wa_test_mode_step_sent" in rec.message for rec in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        tell_reply = handle_inbound_reply(db, from_phone=phone, body="Long wait time", org_id=org_id)
    assert tell_reply.get("handled") is True
    assert tell_reply.get("next_step") == 2
    assert tell_reply.get("payload_source") == "builder_step_sequence"

    caplog.clear()
    with caplog.at_level(logging.INFO):
        final = handle_inbound_reply(db, from_phone=phone, body="Yes", org_id=org_id)
    assert final.get("completed") is True
    assert any("wa_test_mode_completed" in rec.message for rec in caplog.records)

    db.refresh(order)
    recipient = db.get(ServiceOrderRecipient, start["recipient_id"])
    assert recipient is not None
    assert str(recipient.status).lower() == "completed"
    session = SurveySessionService.get_by_recipient(db, recipient.id)
    assert session is not None
    assert str(session.status).lower() == "completed"
    assert mock_send.call_count >= 5


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_dispatch_service.TelnyxMessagingService.is_configured")
def test_live_dispatch_uses_send_survey_opening_for_builder(mock_ready, mock_send, db, org):
    mock_ready.return_value = {"enabled": True, "whatsapp": True, "sms": True}
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, _welcome, _rating, _follow, _tell, _thank, org_id = _seed_multi_step_order(db, org.id)
    order.status = "running"
    db.add(order)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900999",
        status="pending",
    )
    db.add(recipient)
    db.commit()

    with patch(
        "app.services.survey_whatsapp_conversation_service.send_survey_opening",
        wraps=__import__(
            "app.services.survey_whatsapp_conversation_service", fromlist=["send_survey_opening"]
        ).send_survey_opening,
    ) as mock_opening:
        result = SurveyDispatchService._dispatch_one(
            db,
            order=order,
            recipient=recipient,
            config=json.loads(order.config_json),
            intro_template="Hi",
            org_name="Clinic",
            organiser="Clinic",
            prefer_whatsapp=True,
            telnyx_ready={"enabled": True, "whatsapp": True, "sms": True},
        )

    assert mock_opening.called
    assert result["status"] == "sent"
    assert result.get("awaiting_start") is True
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    assert session is not None
    assert int(session.current_step or 0) == 0
