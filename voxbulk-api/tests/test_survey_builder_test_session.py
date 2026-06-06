"""Builder Step 5 WA test — stateful session (welcome only, replies advance)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_test_service import SurveyBuilderTestService
from app.services.survey_whatsapp_conversation_service import (
    find_active_recipient,
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


def _seed_org_user(db) -> tuple[str, str]:
    org = Organisation(name="Test Org")
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return org.id, user.id


def _draft_order(db, *, org_id: str, user_id: str) -> ServiceOrder:
    config = {
        "delivery": "whatsapp",
        "wa_template_id": 101,
        "whatsapp_flow": {
            "intro": "Welcome",
            "closing": "Thanks",
            "questions": [
                {"text": "Rate us 0-10", "reply_type": "rating", "options": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]},
                {"text": "Recommend?", "reply_type": "yes_no", "options": ["Yes", "No"]},
            ],
        },
    }
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title="WA builder test",
        status="draft",
        payment_status="unpaid",
        config_json=json.dumps(config),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    return order


@patch("app.services.survey_builder_test_service.send_survey_opening")
def test_start_wa_test_session_sends_welcome_only(mock_opening, db):
    def _mark_intro_sent(db, *, order, recipient, config):
        recipient.status = "sent"
        recipient.result_json = json.dumps(
            {
                "channel": "whatsapp",
                "wa_conversation": {
                    "step": 0,
                    "total": 2,
                    "answers": [],
                    "intro_sent_at": datetime.utcnow().isoformat(),
                },
            }
        )
        db.add(recipient)
        db.commit()
        return True

    mock_opening.side_effect = _mark_intro_sent
    org_id, user_id = _seed_org_user(db)
    order = _draft_order(db, org_id=org_id, user_id=user_id)

    result = SurveyBuilderTestService.start_wa_test_session(
        db,
        org_id=org_id,
        user_id=user_id,
        order_id=order.id,
        test_phone="+447700900123",
        first_name="Alex",
        business_name="Cafe Live",
    )

    assert result["mode"] == "session"
    assert result["sent"] == 1
    assert mock_opening.call_count == 1
    db.refresh(order)
    assert order.status == "running"
    cfg = json.loads(order.config_json or "{}")
    assert cfg.get("wa_builder_test") is True
    assert cfg.get("test_mode") is True

    found_order, recipient = find_active_recipient(db, from_phone="+447700900123", org_id=org_id)
    assert found_order is not None
    assert recipient is not None


@patch("app.services.survey_whatsapp_conversation_service._send_message")
def test_builder_test_reply_advances_sequentially(mock_send, db):
    mock_send.return_value = True
    org_id, user_id = _seed_org_user(db)
    order = _draft_order(db, org_id=org_id, user_id=user_id)

    with patch("app.services.survey_builder_test_service.send_survey_opening") as mock_opening:
        def _mark_intro_sent(db, *, order, recipient, config):
            recipient.status = "sent"
            recipient.result_json = json.dumps(
                {
                    "channel": "whatsapp",
                    "wa_conversation": {
                        "step": 0,
                        "total": 2,
                        "answers": [],
                        "intro_sent_at": datetime.utcnow().isoformat(),
                    },
                }
            )
            db.add(recipient)
            db.commit()
            return True

        mock_opening.side_effect = _mark_intro_sent
        SurveyBuilderTestService.start_wa_test_session(
            db,
            org_id=org_id,
            user_id=user_id,
            order_id=order.id,
            test_phone="+447700900123",
        )

    first = handle_inbound_reply(db, from_phone="+447700900123", body="Start", org_id=org_id)
    assert first.get("handled") is True
    assert first.get("started") is True

    second = handle_inbound_reply(db, from_phone="+447700900123", body="8", org_id=org_id)
    assert second.get("handled") is True
    assert mock_send.call_count >= 1
