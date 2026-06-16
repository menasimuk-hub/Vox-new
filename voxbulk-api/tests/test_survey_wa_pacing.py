"""WhatsApp survey outbound message pacing."""

from __future__ import annotations

from unittest.mock import patch

import pytest


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
        yield session
    finally:
        session.close()


from app.services.survey_wa_pacing_service import (
    PACING_BRANCH,
    PACING_STEP,
    pause_before_outbound,
    resolve_outbound_delay_seconds,
)


def test_resolve_outbound_delay_seconds_none_is_immediate():
    assert resolve_outbound_delay_seconds(None) == 0.0
    assert resolve_outbound_delay_seconds("") == 0.0


def test_resolve_outbound_delay_seconds_step_and_branch(monkeypatch):
    monkeypatch.setenv("WA_SURVEY_STEP_DELAY_SECONDS", "2")
    monkeypatch.setenv("WA_SURVEY_BRANCH_DELAY_SECONDS", "3.5")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert resolve_outbound_delay_seconds(PACING_STEP) == 2.0
    assert resolve_outbound_delay_seconds(PACING_BRANCH) == 3.5
    get_settings.cache_clear()


@patch("app.services.survey_wa_pacing_service.time.sleep")
def test_pause_before_outbound_sleeps_for_step(mock_sleep):
    with patch(
        "app.services.survey_wa_pacing_service.resolve_outbound_delay_seconds",
        return_value=2.0,
    ):
        pause_before_outbound(pacing=PACING_STEP, order_id="ord-1", recipient_id="rec-1")
    mock_sleep.assert_called_once_with(2.0)


@patch("app.services.survey_wa_pacing_service.time.sleep")
def test_pause_before_outbound_skips_when_disabled(mock_sleep):
    pause_before_outbound(pacing=PACING_STEP, skip=True)
    mock_sleep.assert_not_called()


@patch("app.services.survey_outcome_send_service.pause_before_outbound")
@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.log_outbound")
def test_outcome_send_pauses_before_whatsapp(mock_log, mock_send, mock_pause, db):
    import json
    import uuid
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.survey_outcome_send_service import SurveyOutcomeSendService
    from app.services.survey_session_service import SurveySessionService

    config = {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "whatsapp_flow": {"intro": "Hi", "closing": "Thanks", "questions": [], "page_roles": ["start", "completion"]},
    }
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Outcome pacing",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        started_at=datetime.utcnow(),
    )
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        row_number=1,
        name="Sam",
        phone="+447700900111",
        status="in_progress",
    )
    db.add_all([order, recipient])
    db.commit()
    session = SurveySessionService.start_linear_session(
        db, order=order, recipient=recipient, config=config, question_count=1
    )

    mock_send.return_value = MagicMock(ok=True, detail="ok", external_id="msg-1", channel="whatsapp")

    SurveyOutcomeSendService.deliver(
        db,
        order=order,
        recipient=recipient,
        session=session,
        outcome_result={"action_type": "send_text", "body": "Thanks {{first_name}}!", "outcome_key": "positive"},
        config=config,
    )

    mock_pause.assert_called_once()
    assert mock_pause.call_args.kwargs.get("pacing") == "step"
