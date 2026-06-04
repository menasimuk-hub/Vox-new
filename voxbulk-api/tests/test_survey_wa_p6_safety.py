"""P6: inbound dedupe, outcome delivery idempotency, observability aggregates."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.survey_outcome_delivery_schema import loads_outcome_delivery
from app.services.survey_outcome_send_service import SurveyOutcomeSendService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_wa_observability_service import SurveyWaObservabilityService
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply, send_first_question
from app.services.survey_whatsapp_inbound_guard import is_duplicate_inbound, mark_inbound_processed
from app.services.platform_catalog_service import PlatformCatalogService


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


def _config(*, page_roles: list[str] | None = None) -> dict:
    roles = page_roles or ["start", "rating", "yes_no", "completion"]
    middle = [r for r in roles if r not in ("start", "completion")]
    questions = [
        {"text": "How was your visit?", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
        {"text": "Would you recommend us?", "reply_type": "true_false", "options": ["Yes", "No"]},
    ]
    return {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "survey_type_id": str(uuid.uuid4()),
        "page_roles": roles,
        "whatsapp_flow": {
            "intro": "Hi",
            "closing": "Thanks",
            "questions": questions[: len(middle)],
            "page_roles": roles,
        },
    }


def _seed_order_recipient(db, *, result_json: dict | None = None):
    config = _config()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="WA survey",
        status="running",
        payment_status="approved",
        recipient_count=1,
        quote_total_pence=2900,
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
        name="Jane",
        phone="+447700900123",
        status="in_progress",
        result_json=json.dumps(result_json or {"wa_conversation": {"step": 1, "total": 2}}),
    )
    db.add(recipient)
    db.commit()
    return order, recipient, config


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_duplicate_inbound_does_not_double_advance(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, detail="ok", external_id="ext-1", channel="whatsapp")
    order, recipient, config = _seed_order_recipient(db)
    send_first_question(db, order=order, recipient=recipient, config=config)

    log_id = 42
    message_id = "msg-dup-001"
    r1 = handle_inbound_reply(
        db,
        from_phone="+447700900123",
        body="5",
        org_id=order.org_id,
        log_id=log_id,
        inbound_message_id=message_id,
    )
    assert r1.get("handled") is True
    assert r1.get("duplicate") is not True

    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert payload["wa_conversation"]["last_processed_inbound_log_id"] == log_id

    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    assert session is not None
    answers_after_first = SurveySessionService.list_answers(db, session.id)
    assert len(answers_after_first) == 1

    r2 = handle_inbound_reply(
        db,
        from_phone="+447700900123",
        body="5",
        org_id=order.org_id,
        log_id=log_id,
        inbound_message_id=message_id,
    )
    assert r2.get("handled") is True
    assert r2.get("duplicate") is True
    assert r2.get("skipped") is True

    db.refresh(recipient)
    answers_after_second = SurveySessionService.list_answers(db, session.id)
    assert len(answers_after_second) == 1


def test_inbound_guard_helpers():
    payload = {"wa_conversation": {}}
    assert is_duplicate_inbound(payload, log_id=1, inbound_message_id=None) is False
    payload = mark_inbound_processed(payload, log_id=1, inbound_message_id="m1")
    assert is_duplicate_inbound(payload, log_id=1, inbound_message_id=None) is True
    assert is_duplicate_inbound(payload, log_id=2, inbound_message_id="m1") is True


@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.log_outbound")
def test_outcome_delivery_idempotent(mock_log, mock_send, db):
    mock_send.return_value = MagicMock(ok=True, detail="ok", external_id="ext-out", channel="whatsapp")
    order, recipient, config = _seed_order_recipient(db)
    session = SurveySessionService.start_linear_session(
        db, order=order, recipient=recipient, config=config, question_count=2
    )
    outcome = {
        "outcome_key": "happy",
        "action_type": "send_text",
        "message_body": "Thanks!",
        "template_id": None,
    }
    r1 = SurveyOutcomeSendService.deliver(
        db, order=order, recipient=recipient, session=session, outcome_result=outcome, config=config
    )
    assert r1.get("ok") is True
    assert r1.get("skipped") is not True

    db.refresh(session)
    delivery = loads_outcome_delivery(session.outcome_delivery_json)
    assert delivery.get("sent_at")
    assert delivery.get("ok") is True
    assert delivery.get("outcome_key") == "happy"

    r2 = SurveyOutcomeSendService.deliver(
        db, order=order, recipient=recipient, session=session, outcome_result=outcome, config=config
    )
    assert r2.get("skipped") is True
    assert mock_send.call_count == 1


def test_observability_overview_counts(db):
    order, recipient, config = _seed_order_recipient(db)
    session = SurveySessionService.start_linear_session(
        db, order=order, recipient=recipient, config=config, question_count=2
    )
    session.status = "completed"
    session.outcome_key = "happy"
    session.outcome_delivery_json = json.dumps(
        {
            "sent_at": datetime.utcnow().isoformat(),
            "ok": True,
            "used_text_fallback": True,
            "template_send_failed": True,
            "outcome_key": "happy",
            "action_type": "send_template",
        }
    )
    session.flow_mode = "graph"
    session.picker_invocation_count = 2
    db.add(session)
    db.commit()

    SurveySessionService._append_decision(
        db,
        session,
        decision_kind="branch_take",
        rule_key="simulator.rating.low",
        from_step=1,
        to_step=2,
        from_role="rating",
        to_role="reason",
        reason="test",
    )
    SurveySessionService._append_decision(
        db,
        session,
        decision_kind="branch_picker_result",
        rule_key="ai_picker.fallback",
        from_step=2,
        to_step=3,
        from_role="reason",
        to_role="outcome_happy",
        reason="test",
        picker="ai_assisted",
    )
    db.commit()

    overview = SurveyWaObservabilityService.overview(db, org_id="org-1", since_days=7)
    assert overview["session_count"] >= 1
    assert overview["outcome_counts"].get("happy", 0) >= 1
    assert overview["text_fallback_count"] >= 1
    assert overview["template_send_failure_count"] >= 1
    assert overview["picker_invocation_count"] >= 2
    assert overview["ai_picker_fallback_count"] >= 1

    detail = SurveyWaObservabilityService.get_session_detail(db, session.id)
    assert detail is not None
    assert detail["session"]["id"] == session.id
    assert len(detail["decisions"]) >= 2
