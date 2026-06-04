from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_whatsapp_conversation_service import (
    format_question_message,
    handle_inbound_reply,
    is_whatsapp_survey_order,
    match_answer,
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


def _wa_survey_order(**kwargs) -> ServiceOrder:
    config = {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "contact_method": "WhatsApp",
        "script_approved": True,
        "organisation_name": "Acme Clinic",
        "survey_organiser_name": "Sam",
        "whatsapp_flow": {
            "intro": "Hi {first_name}, quick survey from {clinic_name}.",
            "closing": "Thanks {first_name}!",
            "questions": [
                {"text": "How was your visit?", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
                {"text": "Would you recommend us?", "reply_type": "true_false", "options": ["Yes", "No"]},
            ],
        },
    }
    row = ServiceOrder(
        id=kwargs.pop("id", str(uuid.uuid4())),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="WA survey",
        status=kwargs.pop("status", "running"),
        payment_status="approved",
        recipient_count=1,
        quote_total_pence=2900,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
        started_at=datetime.utcnow(),
    )
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_is_whatsapp_survey_order():
    order = _wa_survey_order()
    assert is_whatsapp_survey_order(order) is True


def test_format_question_message_lists_options():
    msg = format_question_message(
        {"text": "Rate us", "reply_type": "rating", "options": ["1", "2", "3"]},
        index=1,
        total=2,
        include_progress=True,
    )
    assert "Question 1 of 2" in msg
    assert "1. 1" in msg


def test_format_question_message_rating_uses_compact_prompt():
    msg = format_question_message(
        {
            "text": "How would you rate {{2}}?",
            "step_role": "rating",
            "reply_type": "choice",
            "options": [str(i) for i in range(11)],
        },
        index=1,
        total=4,
        variables={"first_name": "Sam", "organisation_name": "Acme Ltd"},
    )
    assert "{{" not in msg
    assert "Acme Ltd" in msg
    assert "0 to 10" in msg
    assert "11. 10" not in msg


def test_match_answer_numeric_choice():
    q = {"text": "Rate", "reply_type": "rating", "options": ["Poor", "Good", "Great"]}
    assert match_answer("2", q) == "Good"


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_handle_inbound_reply_completes_flow(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    order = _wa_survey_order()
    db.add(order)
    db.commit()

    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Jane Doe",
        phone="+447700900123",
        email="jane@example.com",
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

    r1 = handle_inbound_reply(db, from_phone="+447700900123", body="5", org_id="org-1")
    assert r1["handled"] is True
    assert r1.get("next_step") == 2

    db.refresh(recipient)
    assert recipient.status == "in_progress"

    r2 = handle_inbound_reply(db, from_phone="+447700900123", body="Yes", org_id="org-1")
    assert r2["handled"] is True
    assert r2.get("completed") is True

    db.refresh(recipient)
    assert recipient.status == "completed"
    payload = json.loads(recipient.result_json or "{}")
    assert len(payload.get("extracted_answers") or []) == 2
