"""Routing tests for ABUU_CONVERSATION_MODE=agent (v1 DeepSeek agent)."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.pipeline import WaiterPipeline


@pytest.fixture
def agent_mode_env():
    env = {
        "ABUU_AGENT_ENABLED": "true",
        "ABUU_CONVERSATION_MODE": "agent",
        "ABUU_AGENT_WAITER_MODE": "false",
        "SMART_PIPELINE_ENABLED": "false",
        "ABUU_DEEPSEEK_ENABLED": "true",
        "ABUU_IGNORE_DISTANCE": "true",
        "ABUU_VOICE_INTERPRETATION_ENABLED": "false",
    }
    with patch.dict(os.environ, env):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture
def abuu_seeded(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        yield db


def test_waiter_v2_disabled_in_agent_mode(agent_mode_env):
    assert WaiterPipeline.enabled_for_phone("+972509990001") is False
    assert AbuuInboundService._agent_mode_enabled() is True
    assert AbuuInboundService._pipeline_name("+972509990001") == "agent"


@patch("app.abuu.services.inbound_service.AbuuAgentLoop.run")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_yallasay_routes_to_agent(mock_send, mock_agent, app_client, abuu_seeded, agent_mode_env):
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_agent.return_value = {"handled": True, "action": "agent_reply", "reply": "أهلاً! شو بدك؟"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Agent Mode Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        customer.name = "Qusay"
        abuu_db.add(customer)
        abuu_db.commit()

    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="Yallasay",
            message_id=f"agent-yalla-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )

    assert result.get("handled") is True
    mock_agent.assert_called_once()
    assert mock_agent.call_args.kwargs.get("input_source") == "text"


@patch("app.abuu.waiter.pipeline.SmartPipeline.handle")
@patch("app.abuu.services.inbound_service.AbuuAgentLoop.run")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_djaj_routes_to_agent_not_smart_pipeline(mock_send, mock_agent, mock_smart, app_client, abuu_seeded, agent_mode_env):
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_agent.return_value = {"handled": True, "action": "agent_reply", "reply": "هاي أطباق الدجاج"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Agent Mode Org 2")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    base_id = uuid.uuid4().hex[:8]

    with get_abuu_sessionmaker()() as abuu_db:
        AbuuOrderDraftService.upsert_session(abuu_db, phone=phone, step="browsing", context={})
        abuu_db.commit()

    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="دجاج",
            message_id=f"agent-djaj-{base_id}",
            org_id=org_id,
        )

    mock_agent.assert_called_once()
    mock_smart.assert_not_called()


@patch("app.abuu.conversation.orchestrator.AbuuConversationOrchestrator.handle")
@patch("app.abuu.services.inbound_service.AbuuAgentLoop.run")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_djaj_skips_orchestrator_in_agent_mode(mock_send, mock_agent, mock_orch, app_client, abuu_seeded, agent_mode_env):
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_agent.return_value = {"handled": True, "action": "agent_reply", "reply": "ok"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Agent Mode Org 3")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    base_id = uuid.uuid4().hex[:8]

    with get_abuu_sessionmaker()() as abuu_db:
        AbuuOrderDraftService.upsert_session(abuu_db, phone=phone, step="browsing", context={})
        abuu_db.commit()

    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="دجاج",
            message_id=f"agent-orch-{base_id}",
            org_id=org_id,
        )

    mock_agent.assert_called_once()
    mock_orch.assert_not_called()


@patch("app.abuu.services.inbound_service.AbuuAgentLoop.run")
@patch("app.abuu.services.inbound_service.AbuuVoiceService.transcribe_inbound")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_voice_routes_to_agent(mock_send, mock_transcribe, mock_agent, app_client, abuu_seeded, agent_mode_env):
    from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_transcribe.return_value = AbuuVoiceTranscription(
        ok=True,
        transcript="بدي دجاج",
        confidence=0.9,
        media_url="https://example.com/voice.ogg",
        content_type="audio/ogg",
        storage_path="/tmp/voice.ogg",
    )
    mock_agent.return_value = {"handled": True, "action": "agent_reply", "reply": "تمام"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Agent Voice Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    voice_record = {
        "type": "audio",
        "media": [{"url": "https://example.com/voice.ogg", "content_type": "audio/ogg"}],
    }

    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="",
            message_id=f"agent-voice-{uuid.uuid4().hex[:8]}",
            record=voice_record,
            org_id=org_id,
        )

    assert result.get("handled") is True
    mock_agent.assert_called_once()
    assert mock_agent.call_args.kwargs.get("input_source") == "voice"
