"""P1: survey session tables wired to linear WhatsApp conversation flow."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession, SurveySessionAnswer, SurveySessionDecision
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_session_service import (
    SurveySessionService,
    build_node_key,
    resolve_step_role,
)
from app.services.survey_whatsapp_conversation_service import (
    handle_inbound_reply,
    send_first_question,
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


def _config(*, page_roles: list[str] | None = None) -> dict:
    roles = page_roles or ["start", "rating", "yes_no", "completion"]
    middle = [r for r in roles if r not in ("start", "completion")]
    questions = [
        {"text": "How was your visit?", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
        {"text": "Would you recommend us?", "reply_type": "true_false", "options": ["Yes", "No"]},
    ]
    if len(middle) == 1:
        questions = questions[:1]
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


def _order(config: dict) -> ServiceOrder:
    return ServiceOrder(
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


def test_resolve_step_role_from_page_roles():
    cfg = _config()
    assert resolve_step_role(cfg, step_index=1, question_count=2) == "rating"
    assert resolve_step_role(cfg, step_index=2, question_count=2) == "yes_no"
    assert build_node_key("rating", 1) == "rating@1"


def test_start_linear_session_creates_decisions(db):
    order = _order(_config())
    db.add(order)
    db.commit()
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Jane",
        phone="+447700900123",
        status="sent",
    )
    db.add(recipient)
    db.commit()

    session = SurveySessionService.start_linear_session(
        db,
        order=order,
        recipient=recipient,
        config=_config(),
        question_count=2,
    )
    assert session.status == "active"
    assert session.total_steps == 2
    decisions = SurveySessionService.list_decisions(db, session.id)
    assert len(decisions) == 2
    assert decisions[0].decision_kind == "start_session"
    assert decisions[1].decision_kind == "send_question"


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_send_first_question_creates_session_and_result_json(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    config = _config()
    order = _order(config)
    db.add(order)
    db.commit()
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Jane",
        phone="+447700900123",
        status="sent",
    )
    db.add(recipient)
    db.commit()

    send_first_question(db, order=order, recipient=recipient, config=config)
    db.refresh(recipient)

    payload = json.loads(recipient.result_json or "{}")
    assert payload["wa_conversation"]["survey_session_id"]
    session = SurveySessionService.get_by_recipient(db, recipient.id)
    assert session is not None
    assert session.flow_mode == "linear"


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_handle_inbound_reply_persists_answers_and_decisions(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    config = _config()
    order = _order(config)
    db.add(order)
    db.commit()
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Jane",
        phone="+447700900123",
        status="in_progress",
        result_json=json.dumps(
            {
                "channel": "whatsapp",
                "wa_conversation": {"step": 1, "total": 2, "answers": []},
            }
        ),
    )
    db.add(recipient)
    db.commit()

    SurveySessionService.start_linear_session(
        db, order=order, recipient=recipient, config=config, question_count=2
    )

    r1 = handle_inbound_reply(db, from_phone="+447700900123", body="5", org_id=order.org_id)
    assert r1["handled"] is True

    session = SurveySessionService.get_by_recipient(db, recipient.id)
    answers = SurveySessionService.list_answers(db, session.id)
    assert len(answers) == 1
    assert answers[0].step_role == "rating"
    assert answers[0].normalized_value == "5"
    assert answers[0].sequence == 1

    r2 = handle_inbound_reply(db, from_phone="+447700900123", body="Yes", org_id=order.org_id)
    assert r2.get("completed") is True

    db.refresh(session)
    assert session.status == "completed"
    answers = SurveySessionService.list_answers(db, session.id)
    assert len(answers) == 2
    decisions = SurveySessionService.list_decisions(db, session.id)
    kinds = [d.decision_kind for d in decisions]
    assert "record_answer" in kinds
    assert "advance_linear" in kinds
    assert "complete_session" in kinds

    payload = json.loads(recipient.result_json or "{}")
    assert len(payload.get("extracted_answers") or []) == 2
    assert payload["wa_conversation"]["survey_session_id"] == session.id
