"""Start button inbound webhook → first builder template send."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_runtime_service import attach_builder_runtime_to_config, build_builder_runtime
from app.services.survey_wa_inbound_parse_service import (
    START_ACTION,
    parse_telnyx_wa_inbound_record,
)
from app.services.survey_whatsapp_conversation_service import (
    handle_inbound_reply,
    send_survey_opening,
    try_handle_survey_whatsapp_inbound,
)
from app.services.telnyx_inbound_messaging_service import TelnyxInboundMessagingService


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


def _tpl(db, *, name: str, body: str, step_role: str, buttons: list[dict] | None = None):
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    components = [{"type": "BODY", "text": body}]
    if buttons:
        components.append({"type": "BUTTONS", "buttons": buttons})
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
        components_json=json.dumps(components),
    )
    db.add(row)
    db.commit()
    return row


def _seed_builder_order(db, org_id: str):
    welcome = _tpl(
        db,
        name="welcome_start",
        body="Hi {{1}}, tap Start to begin.",
        step_role="start",
        buttons=[{"type": "QUICK_REPLY", "text": "Start", "id": "start-btn-id"}],
    )
    q1 = _tpl(db, name="middle_q1", body="Rate us {{1}}", step_role="rating")
    q2 = _tpl(db, name="middle_q2", body="Would you return?", step_role="yes_no")
    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[q1.id, q2.id],
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
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
        started_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        row_number=1,
        name="Live",
        phone="+447700900123",
        status="pending",
    )
    db.add(recipient)
    db.commit()
    return order, recipient, runtime, q1, welcome


def _telnyx_button_payload(*, title: str, button_id: str = "start-btn-id") -> dict:
    return {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "direction": "inbound",
        "type": "whatsapp",
        "from": {"phone_number": "+447700900123"},
        "to": [{"phone_number": "+442046203055"}],
        "body": button_id,
        "whatsapp_message": {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": button_id, "title": title},
            },
        },
    }


def _telnyx_payload_only(button_id: str) -> dict:
    return {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "direction": "inbound",
        "type": "whatsapp",
        "from": {"phone_number": "+447700900123"},
        "to": [{"phone_number": "+442046203055"}],
        "body": button_id,
        "whatsapp_message": {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": button_id, "title": ""},
            },
        },
    }


def _telnyx_text_start() -> dict:
    return {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "direction": "inbound",
        "type": "whatsapp",
        "from": {"phone_number": "+447700900123"},
        "to": [{"phone_number": "+442046203055"}],
        "body": {"type": "text", "text": {"body": "Start"}},
    }


@pytest.fixture()
def org(db):
    org = Organisation(name="Start Button Org")
    db.add(org)
    db.commit()
    return org


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_start_button_title_advances_to_first_middle_template(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, recipient, runtime, q1, _welcome = _seed_builder_order(db, org.id)

    assert send_survey_opening(db, order=order, recipient=recipient, config=json.loads(order.config_json))

    record = _telnyx_button_payload(title="Start")
    normalized = parse_telnyx_wa_inbound_record(record, sender_phone=recipient.phone or "")
    assert normalized.normalized_action == START_ACTION

    result = handle_inbound_reply(
        db,
        from_phone=recipient.phone or "",
        body=normalized.normalized_answer,
        org_id=org.id,
        inbound_reply=normalized,
    )
    assert result.get("handled") is True
    assert result.get("started") is True
    assert result.get("action") == START_ACTION
    assert result.get("next_template_id") == q1.id
    assert mock_send.call_count >= 2


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_start_button_payload_only(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, recipient, _runtime, q1, welcome = _seed_builder_order(db, org.id)
    send_survey_opening(db, order=order, recipient=recipient, config=json.loads(order.config_json))

    record = _telnyx_payload_only("start-btn-id")
    normalized = parse_telnyx_wa_inbound_record(record, sender_phone=recipient.phone or "")
    result = handle_inbound_reply(
        db,
        from_phone=recipient.phone or "",
        body=normalized.normalized_answer,
        org_id=org.id,
        inbound_reply=normalized,
    )
    assert result.get("started") is True
    assert result.get("next_template_id") == q1.id


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_start_plain_text_fallback(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, recipient, _runtime, q1, _welcome = _seed_builder_order(db, org.id)
    send_survey_opening(db, order=order, recipient=recipient, config=json.loads(order.config_json))

    result = handle_inbound_reply(
        db,
        from_phone=recipient.phone or "",
        body="Start",
        org_id=org.id,
    )
    assert result.get("started") is True
    assert result.get("next_template_id") == q1.id


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_telnyx_webhook_route_start_click(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, recipient, _runtime, q1, _welcome = _seed_builder_order(db, org.id)
    send_survey_opening(db, order=order, recipient=recipient, config=json.loads(order.config_json))

    record = _telnyx_button_payload(title="Start")
    webhook = {"data": {"event_type": "message.received", "payload": record}}
    result = TelnyxInboundMessagingService.handle_webhook(
        db,
        webhook,
        header_org_id=org.id,
    )
    assert result.get("ok") is True
    db.refresh(recipient)
    conv = json.loads(recipient.result_json or "{}").get("wa_conversation") or {}
    assert int(conv.get("step") or 0) == 1


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_unparsed_start_hard_fails(mock_send, db, org):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    order, recipient, _runtime, _q1, _welcome = _seed_builder_order(db, org.id)
    send_survey_opening(db, order=order, recipient=recipient, config=json.loads(order.config_json))

    result = handle_inbound_reply(
        db,
        from_phone=recipient.phone or "",
        body="hello there",
        org_id=org.id,
    )
    assert result.get("handled") is False
    assert result.get("reason") == "awaiting_start_unparsed"
