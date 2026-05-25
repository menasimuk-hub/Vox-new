from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_call_dispatch_service import (
    SurveyCallDispatchService,
    _handle_survey_voicemail,
    _is_voicemail_telnyx_event,
    _resolve_voicemail_behavior,
    build_survey_call_greeting,
    build_survey_call_instructions,
    is_ai_call_survey_order,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def _survey_order(**kwargs) -> ServiceOrder:
    config = {
        "survey_channel": "ai_call",
        "channels": ["call"],
        "contact_method": "AI phone call",
        "script_approved": True,
        "approved_script": "INTRO\nHello {first_name}\n\nQUESTIONS\n1. How was your visit?\n\nCLOSING\nThank you",
        "system_prompt": "Run a polite survey.",
        "organisation_name": "Acme Clinic",
        "survey_organiser_name": "Sam",
    }
    row = ServiceOrder(
        id=kwargs.pop("id", str(uuid.uuid4())),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Test survey",
        status=kwargs.pop("status", "scheduled"),
        payment_status=kwargs.pop("payment_status", "approved"),
        recipient_count=1,
        quote_total_pence=2900,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=kwargs.pop("scheduled_start_at", datetime.utcnow() - timedelta(minutes=5)),
        scheduled_end_at=kwargs.pop("scheduled_end_at", datetime.utcnow() + timedelta(hours=2)),
    )
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_is_ai_call_survey_order():
    order = _survey_order()
    assert is_ai_call_survey_order(order) is True
    order.service_code = "interview"
    assert is_ai_call_survey_order(order) is False


def test_build_survey_call_instructions_personalizes():
    config = json.loads(_survey_order().config_json)
    text = build_survey_call_instructions(config, recipient_name="Jane Doe")
    assert "Jane" in text
    assert "Acme Clinic" in text
    assert "Run a polite survey" in text


def test_build_survey_call_greeting():
    config = json.loads(_survey_order().config_json)
    greeting = build_survey_call_greeting(config, recipient_name="Jane Doe")
    assert "Jane" in greeting


def test_start_campaign_marks_running(db, monkeypatch):
    order = _survey_order()
    db.add(order)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_voice_agent_service.resolve_survey_telnyx_assistant_id",
        lambda _db, _order, _config: ("assistant-123", None),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service._order_window_ok",
        lambda _order, now=None: (True, None),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.SurveyCallDispatchService.dial_next_recipient",
        lambda _db, _order: MagicMock(),
    )

    started = SurveyCallDispatchService.start_campaign(db, order)
    assert started is True
    db.refresh(order)
    assert order.status == "running"
    assert order.started_at is not None


def test_dial_next_recipient_sets_calling(db, monkeypatch):
    order = _survey_order(status="running", started_at=datetime.utcnow())
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="pending",
    )
    db.add(recipient)
    db.commit()

    class FakeResult:
        ok = True
        status = "queued"
        external_id = "call-ctrl-1"
        detail = None

    monkeypatch.setattr(
        "app.services.survey_voice_agent_service.resolve_survey_telnyx_assistant_id",
        lambda _db, _order, _config: ("assistant-123", None),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service._order_window_ok",
        lambda _order, now=None: (True, None),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.telnyx_outbound_caller_id",
        lambda _cfg: "+447700900000",
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service._telnyx_config",
        lambda _db: {"api_key": "k", "connection_id": "c"},
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.TelnyxVoiceAdapter.start_outbound_call",
        lambda **kwargs: FakeResult(),
    )

    row = SurveyCallDispatchService.dial_next_recipient(db, order)
    assert row is not None
    db.refresh(recipient)
    assert recipient.status == "calling"
    result = json.loads(recipient.result_json or "{}")
    assert result.get("call_control_id") == "call-ctrl-1"


def test_process_due_orders_starts_eligible(db, monkeypatch):
    order = _survey_order()
    db.add(order)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.SurveyCallDispatchService.start_campaign",
        lambda _db, _order: True,
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.SurveyCallDispatchService.tick_running_order",
        lambda _db, _order: None,
    )

    count = SurveyCallDispatchService.process_due_orders(db)
    assert count >= 1


def test_voicemail_detection_helpers():
    assert _is_voicemail_telnyx_event("call.machine.detection.ended", {"result": "machine"}) is True
    assert _is_voicemail_telnyx_event("call.answered", {"hangup_cause": "answering_machine"}) is True
    assert _is_voicemail_telnyx_event("call.answered", {"result": "human"}) is False


def test_resolve_voicemail_behavior_prefers_client_state():
    class Agent:
        voicemail_behavior = "hang_up"

    assert _resolve_voicemail_behavior({"voicemail_behavior": "leave_message"}, Agent()) == "leave_message"
    assert _resolve_voicemail_behavior({}, Agent()) == "hang_up"


def test_dial_next_recipient_includes_voicemail_behavior(db, monkeypatch):
    from app.models.agent import AgentDefinition

    agent = AgentDefinition(
        name="Sophie",
        slug="sophie-test",
        system_prompt="Test",
        is_active=True,
        supports_survey=True,
        voicemail_behavior="retry_later",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()

    order = _survey_order(status="running", started_at=datetime.utcnow())
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="pending",
    )
    db.add(recipient)
    db.commit()

    captured = {}

    class FakeResult:
        ok = True
        status = "queued"
        external_id = "call-ctrl-1"
        detail = None

    monkeypatch.setattr(
        "app.services.survey_voice_agent_service.resolve_survey_telnyx_assistant_id",
        lambda _db, _order, _config: ("assistant-123", agent),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service._order_window_ok",
        lambda _order, now=None: (True, None),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.telnyx_outbound_caller_id",
        lambda _cfg: "+447700900000",
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service._telnyx_config",
        lambda _db: {"api_key": "k", "connection_id": "c"},
    )

    def capture_call(**kwargs):
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.TelnyxVoiceAdapter.start_outbound_call",
        capture_call,
    )

    SurveyCallDispatchService.dial_next_recipient(db, order)
    state = captured.get("client_state") or {}
    assert state.get("voicemail_behavior") == "retry_later"


def test_handle_voicemail_hang_up(db, monkeypatch):
    order = _survey_order(status="running", started_at=datetime.utcnow())
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="calling",
        result_json="{}",
    )
    db.add(recipient)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.TelnyxVoiceAdapter.hangup_call",
        lambda **kwargs: MagicMock(ok=True, status="hangup_sent"),
    )
    monkeypatch.setattr(
        "app.services.survey_call_dispatch_service.SurveyCallDispatchService.dial_next_recipient",
        lambda *_args, **_kwargs: None,
    )

    handled = _handle_survey_voicemail(
        db,
        order=order,
        recipient=recipient,
        call_id="call-1",
        parsed={"voicemail_behavior": "hang_up"},
        agent=None,
        config_order=json.loads(order.config_json),
        telnyx_config={"api_key": "k"},
        assistant_id="assistant-123",
        behavior="hang_up",
    )
    assert handled is True
    db.refresh(recipient)
    assert recipient.status == "no_answer"
