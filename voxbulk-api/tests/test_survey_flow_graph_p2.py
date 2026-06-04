"""P2: deterministic graph flow — compile, validate, runtime."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_flow_compiler_service import compile_linear_graph, validate_flow_snapshot
from app.services.survey_flow_condition_service import evaluate_condition
from app.services.survey_flow_config_service import attach_flow_to_config, is_graph_flow
from app.services.survey_flow_constants import OUTCOME_UNHAPPY
from app.services.survey_flow_engine_service import SurveyFlowEngineService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply, send_first_question


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


def _graph_config(*, branches: list[dict] | None = None) -> dict:
    page_roles = ["start", "rating", "yes_no", "completion"]
    questions = [
        {"step_role": "rating", "text": "Rate us", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
        {"step_role": "yes_no", "text": "Recommend?", "reply_type": "true_false", "options": ["Yes", "No"]},
    ]
    snap = compile_linear_graph(
        page_roles=page_roles,
        questions=questions,
        max_question_visits=5,
        closing_body="Thanks!",
        branches=branches
        or [
            {
                "from_step_role": "rating",
                "to_step_role": "unhappy",
                "priority": 5,
                "rule_key": "branch.rating.low",
                "condition": {
                    "op": "lte",
                    "source": "last_answer.normalized_value",
                    "value": "2",
                    "cast": "int",
                },
            },
        ],
    )
    base = {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "survey_type_id": str(uuid.uuid4()),
        "page_roles": page_roles,
        "page_count": 5,
        "whatsapp_flow": {"intro": "Hi", "closing": "Thanks!", "questions": questions, "page_roles": page_roles},
    }
    return attach_flow_to_config(base, snapshot=snap, flow_definition_id=None)


def _order(config: dict) -> ServiceOrder:
    return ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Graph survey",
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


def test_compile_linear_graph_validates():
    snap = compile_linear_graph(
        page_roles=["start", "rating", "completion"],
        questions=[{"step_role": "rating", "text": "Rate", "reply_type": "rating", "options": ["1", "2"]}],
        max_question_visits=4,
        closing_body="Bye",
    )
    errors = validate_flow_snapshot(snap)
    assert errors == []


def test_condition_lte_on_normalized_value():
    class FakeAnswer:
        normalized_value = "2"
        raw_value = "2"
        step_role = "rating"

    assert evaluate_condition(
        {"op": "lte", "source": "last_answer.normalized_value", "value": "3", "cast": "int"},
        last_answer=FakeAnswer(),
        answers=[FakeAnswer()],
    )


def test_is_graph_flow_requires_snapshot():
    assert is_graph_flow({"flow_engine": "graph"}) is False
    cfg = _graph_config()
    assert is_graph_flow(cfg) is True


@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_graph_low_rating_routes_to_unhappy(mock_send, mock_wa, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    mock_wa.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok", external_id="ext-1")
    config = _graph_config()
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
    session = SurveySessionService.get_by_recipient(db, recipient.id)
    assert session is not None
    assert session.flow_mode == "graph"
    assert session.current_node_key == "rating"

    r1 = handle_inbound_reply(db, from_phone="+447700900123", body="1", org_id=order.org_id)
    assert r1["handled"] is True
    assert r1.get("completed") is True
    assert r1.get("outcome_key") == OUTCOME_UNHAPPY

    db.refresh(session)
    assert session.status == "completed"
    assert session.outcome_key == OUTCOME_UNHAPPY
    decisions = SurveySessionService.list_decisions(db, session.id)
    kinds = [d.decision_kind for d in decisions]
    assert "branch_take" in kinds
    assert "outcome_reached" in kinds


@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_graph_high_rating_continues_then_completes(mock_send, mock_wa, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    mock_wa.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok", external_id="ext-2")
    config = _graph_config(branches=[])
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
    r1 = handle_inbound_reply(db, from_phone="+447700900123", body="5", org_id=order.org_id)
    assert r1["handled"] is True
    assert not r1.get("completed")

    r2 = handle_inbound_reply(db, from_phone="+447700900123", body="Yes", org_id=order.org_id)
    assert r2.get("completed") is True
    session = SurveySessionService.get_by_recipient(db, recipient.id)
    assert session.outcome_key == "neutral"
