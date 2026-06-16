"""Tests for always-on Abuu agent trace logging."""

from __future__ import annotations

import logging
import os
import uuid
from unittest.mock import patch

import pytest

from app.abuu import agent_trace
from app.abuu.services.inbound_service import AbuuInboundService
from app.services.agents.base import AgentToolCall
from app.services.providers.openai_service import OpenAIResponse


@pytest.fixture
def agent_mode_env():
    env = {
        "ABUU_ENABLED": "true",
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


def test_agent_trace_emits_stt_ok(caplog):
    caplog.set_level(logging.INFO, logger="app.abuu.agent_trace")
    agent_trace.stt_ok(
        phone="+972500000001",
        msg_id="msg-1",
        transcript="بدي دجاج",
        confidence=0.9,
    )
    hits = [r for r in caplog.records if "abuu_agent_trace stt_ok" in r.message]
    assert hits
    assert "msg_id=msg-1" in hits[0].message
    assert "transcript=" in hits[0].message


def test_agent_trace_emits_route_and_turn_end(caplog):
    caplog.set_level(logging.INFO, logger="app.abuu.agent_trace")
    agent_trace.route(
        phone="+972500000001",
        msg_id="msg-2",
        pipeline="agent",
        voice=True,
        text="بدي عرض",
    )
    agent_trace.turn_end(
        phone="+972500000001",
        msg_id="msg-2",
        action="agent_reply",
        reply_preview="هاي العروض",
    )
    messages = [r.message for r in caplog.records if "abuu_agent_trace" in r.message]
    assert any("abuu_agent_trace route" in m for m in messages)
    assert any("abuu_agent_trace turn_end" in m for m in messages)


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_agent_loop_emits_llm_tool_and_reply(mock_complete, app_client, agent_mode_env):
    from app.abuu.agent.agent import AbuuAgentLoop
    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.abuu.services.seed_service import AbuuSeedService
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    tool_id = "call_trace_1"
    tool_response = OpenAIResponse(
        assistant_text="",
        tool_calls=[
            AgentToolCall(id=tool_id, name="list_offers", arguments={}),
        ],
        raw_assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {"name": "list_offers", "arguments": "{}"},
                }
            ],
        },
        finish_reason="tool_calls",
    )
    final_response = OpenAIResponse(
        assistant_text="هاي العروض المتاحة",
        raw_assistant_message={"role": "assistant", "content": "هاي العروض المتاحة"},
        finish_reason="stop",
    )
    mock_complete.side_effect = [tool_response, final_response]

    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({"api_key": "test-key"}, True),
    ), patch("app.abuu.agent.agent.agent_trace") as mock_trace:
        phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
        msg_id = f"trace-{uuid.uuid4().hex[:8]}"
        with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
            AbuuSeedService.seed_restaurants_if_empty(abuu_db)
            AbuuSeedService.seed_offers_if_empty(abuu_db)
            seed_agent_settings(abuu_db)
            abuu_db.commit()
            result = AbuuAgentLoop.run(
                abuu_db,
                main_db,
                phone=phone,
                text="شو العروض",
                message_id=msg_id,
                input_source="text",
            )

    assert result["action"] == "agent_reply"
    mock_trace.turn_start.assert_called_once()
    mock_trace.prefetch.assert_called_once()
    mock_trace.llm_request.assert_called()
    mock_trace.llm_tool.assert_called_once()
    tool_kwargs = mock_trace.llm_tool.call_args.kwargs
    assert tool_kwargs.get("tool") == "list_offers"
    mock_trace.llm_reply.assert_called_once()


@patch("app.abuu.services.inbound_service.AbuuAgentLoop.run")
@patch("app.abuu.services.inbound_service.AbuuVoiceService.transcribe_inbound")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_voice_inbound_emits_stt_ok_and_route(
    mock_send,
    mock_transcribe,
    mock_agent,
    app_client,
    agent_mode_env,
):
    from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription
    from app.abuu.services.seed_service import AbuuSeedService
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_transcribe.return_value = AbuuVoiceTranscription(
        ok=True,
        transcript="بدي عرض البحر العائلي",
        confidence=0.9,
        media_url="https://example.com/voice.ogg",
        content_type="audio/ogg",
        storage_path="/tmp/voice.ogg",
    )
    mock_agent.return_value = {"handled": True, "action": "agent_reply", "reply": "هاي العروض"}

    with get_abuu_sessionmaker()() as abuu_db:
        AbuuSeedService.seed_restaurants_if_empty(abuu_db)
        abuu_db.commit()

    with get_sessionmaker()() as db:
        org = Organisation(name="Trace Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    msg_id = f"voice-trace-{uuid.uuid4().hex[:8]}"
    voice_record = {
        "type": "audio",
        "media": [{"url": "https://example.com/voice.ogg", "content_type": "audio/ogg"}],
    }

    with patch("app.abuu.services.inbound_service.agent_trace") as mock_trace:
        with get_sessionmaker()() as db:
            result = AbuuInboundService.try_handle(
                db,
                from_phone=phone,
                body="",
                message_id=msg_id,
                record=voice_record,
                org_id=org_id,
            )

    assert result.get("handled") is True
    mock_trace.stt_ok.assert_called_once()
    assert mock_trace.stt_ok.call_args.kwargs.get("msg_id") == msg_id
    clip_texts = [call.args[0] for call in mock_trace.clip.call_args_list if call.args]
    assert any("عرض" in text for text in clip_texts)
    mock_trace.route.assert_called_once()
    route_kwargs = mock_trace.route.call_args.kwargs
    assert route_kwargs.get("pipeline") == "agent"
    assert route_kwargs.get("voice") is True
    mock_trace.turn_end.assert_called_once()
