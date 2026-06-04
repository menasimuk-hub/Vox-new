"""Survey-only WhatsApp workflow: routing, org scope, bootstrap idempotency, opt-out."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.organisation import Organisation
from app.models.org_opt_out import OrganisationOptOut
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_whatsapp_conversation_service import (
    bootstrap_after_intro,
    find_active_recipient,
    handle_inbound_reply,
    handle_survey_wa_opt_out,
    is_survey_wa_opt_out_message,
    send_first_question,
    try_handle_survey_whatsapp_inbound,
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


def _wa_config() -> dict:
    return {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "whatsapp_flow": {
            "intro": "Hi",
            "closing": "Thanks",
            "questions": [
                {"text": "Rate us", "reply_type": "rating", "options": ["1", "2", "3"]},
                {"text": "Recommend?", "reply_type": "yes_no", "options": ["Yes", "No"]},
            ],
        },
    }


def _order_recipient(
    db,
    *,
    org_id: str,
    phone: str = "+447700900123",
    result_json: dict | None = None,
) -> tuple[ServiceOrder, ServiceOrderRecipient, dict]:
    config = _wa_config()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
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
        phone=phone,
        status="in_progress",
        result_json=json.dumps(
            result_json
            or {"channel": "whatsapp", "wa_conversation": {"step": 1, "total": 2, "answers": []}}
        ),
    )
    db.add(recipient)
    db.commit()
    return order, recipient, config


def _seed_org(db, name: str) -> str:
    org = Organisation(name=name)
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return org.id


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_try_handle_survey_routes_reply_to_survey_flow(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org_id = _seed_org(db, "Org A")
    order, recipient, _config = _order_recipient(db, org_id=org_id)

    routed = try_handle_survey_whatsapp_inbound(
        db,
        from_phone=recipient.phone,
        body="2",
        org_id=org_id,
        log_id=99,
    )
    assert routed is not None
    assert routed.get("handled") is True
    assert routed.get("order_id") == order.id


def test_wrong_org_does_not_match_recipient(db):
    org_a = _seed_org(db, "Org A")
    org_b = _seed_org(db, "Org B")
    _order_recipient(db, org_id=org_a, phone="+447700900111")
    order_b, recipient_b, _ = _order_recipient(db, org_id=org_b, phone="+447700900111")

    found_order, found_recipient = find_active_recipient(
        db, from_phone="+447700900111", org_id=org_b
    )
    assert found_order is not None
    assert found_recipient.id == recipient_b.id
    assert found_order.org_id == org_b

    wrong_order, wrong_recipient = find_active_recipient(
        db, from_phone="+447700900111", org_id=org_a
    )
    assert wrong_order is not None
    assert wrong_recipient is not None
    assert wrong_order.org_id == org_a
    assert wrong_recipient.id != recipient_b.id


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_duplicate_bootstrap_does_not_reset_answers(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, channel="whatsapp", detail="ok")
    org_id = _seed_org(db, "Bootstrap Org")
    order, recipient, config = _order_recipient(
        db,
        org_id=org_id,
        result_json={
            "channel": "whatsapp",
            "wa_conversation": {
                "step": 1,
                "total": 2,
                "answers": [{"question": "Rate us", "answer": "3"}],
                "started_at": datetime.utcnow().isoformat(),
            },
        },
    )

    bootstrap_after_intro(db, order=order, recipient=recipient, config=config)
    db.refresh(recipient)
    payload = json.loads(recipient.result_json or "{}")
    assert len(payload["wa_conversation"]["answers"]) == 1
    assert payload["wa_conversation"]["step"] == 1
    mock_send.assert_not_called()

    send_first_question(db, order=order, recipient=recipient, config=config)
    mock_send.assert_not_called()


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_opt_out_not_saved_as_survey_answer(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, channel="whatsapp", detail="ok")
    org_id = _seed_org(db, "Opt-out Org")
    order, recipient, _config = _order_recipient(db, org_id=org_id, result_json={"channel": "whatsapp"})

    assert is_survey_wa_opt_out_message("STOP") is True
    assert is_survey_wa_opt_out_message("stopall") is True
    assert is_survey_wa_opt_out_message("5") is False

    result = handle_survey_wa_opt_out(
        db,
        from_phone=recipient.phone,
        body="STOP",
        org_id=org_id,
        log_id=50,
    )
    assert result.get("handled") is True
    assert result.get("opted_out") is True

    db.refresh(recipient)
    assert recipient.status == "opted_out"
    payload = json.loads(recipient.result_json or "{}")
    assert not payload.get("extracted_answers")
    assert "STOP" not in str(payload.get("wa_conversation", {}).get("answers", ""))

    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if session:
        answers = SurveySessionService.list_answers(db, session.id)
        assert len(answers) == 0

    opted = db.execute(
        select(OrganisationOptOut).where(OrganisationOptOut.org_id == org_id)
    ).scalar_one_or_none()
    assert opted is not None

    routed = try_handle_survey_whatsapp_inbound(
        db,
        from_phone=recipient.phone,
        body="Yes",
        org_id=org_id,
    )
    assert routed is None or routed.get("handled") is False


def test_telnyx_inbound_survey_routed_before_interview():
    from app.services import telnyx_inbound_messaging_service as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "try_handle_survey_whatsapp_inbound" in source
    assert source.index("try_handle_survey_whatsapp_inbound") < source.index(
        "handle_interview_booking_reply"
    )
