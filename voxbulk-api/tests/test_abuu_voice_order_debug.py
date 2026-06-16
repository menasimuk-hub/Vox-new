from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.abuu.models.entities import AbuuVoiceOrderDebug, CustomerOrder
from app.abuu.services.voice_order_debug_service import VoiceOrderDebugService, set_debug_request_id
from app.abuu.services.voice_order_replay_service import VoiceOrderReplayService
from app.core.config import get_settings


@pytest.fixture
def voice_debug_enabled():
    with patch.dict(os.environ, {"ABUU_VOICE_ORDER_DEBUG": "true"}):
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def abuu_db(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        yield db


def test_debug_service_records_all_stages(abuu_db, voice_debug_enabled):
    request_id = VoiceOrderDebugService.begin(
        abuu_db,
        customer_phone="+972509990100",
        message_id="msg-voice-1",
        pipeline="agent",
    )
    assert request_id

    VoiceOrderDebugService.record_audio(
        abuu_db,
        media_url="https://example.com/voice.ogg",
        storage_path="/tmp/voice.ogg",
        content_type="audio/ogg",
        file_size_bytes=12345,
        duration_seconds=4.2,
    )
    VoiceOrderDebugService.record_stt(abuu_db, raw_transcript="بدي عرض السمك")
    VoiceOrderDebugService.record_llm_prompt(
        abuu_db,
        system_prompt="system prompt here",
        messages=[{"role": "user", "content": "بدي عرض السمك"}],
        session_snapshot={"stage": "browsing"},
    )
    VoiceOrderDebugService.record_llm_raw(abuu_db, raw_response='{"reply":"تمام"}')
    VoiceOrderDebugService.record_parsed(
        abuu_db,
        parsed={"pipeline": "agent", "reply": "تمام"},
        parse_status="ok",
    )
    abuu_db.commit()

    bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)
    assert bundle is not None
    stages = bundle["stages"]
    assert stages["1_audio"]["file_size_bytes"] == 12345
    assert stages["2_stt_raw"]["transcript"] == "بدي عرض السمك"
    assert "system prompt" in stages["3_llm_prompt"]["system_prompt"]
    assert stages["4_llm_raw"]["response"] == {"reply": "تمام"}
    assert stages["5_parsed"]["parse_status"] == "ok"


def test_get_bundle_missing_returns_none(abuu_db, voice_debug_enabled):
    assert VoiceOrderDebugService.get_bundle(abuu_db, str(uuid.uuid4())) is None


def test_begin_disabled_when_flag_off(abuu_db):
    with patch.dict(os.environ, {"ABUU_VOICE_ORDER_DEBUG": "false"}):
        get_settings.cache_clear()
        assert VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone="+972509990101",
            message_id="msg-1",
            pipeline="agent",
        ) is None
    get_settings.cache_clear()


def test_replay_dry_run_does_not_create_orders(abuu_db, voice_debug_enabled):
    request_id = VoiceOrderDebugService.begin(
        abuu_db,
        customer_phone="+972509990102",
        message_id="msg-voice-2",
        pipeline="smart",
    )
    VoiceOrderDebugService.record_audio(
        abuu_db,
        media_url="https://example.com/voice.ogg",
        storage_path="/tmp/missing-voice.ogg",
        content_type="audio/ogg",
        file_size_bytes=100,
        duration_seconds=1.0,
    )
    VoiceOrderDebugService.record_stt(abuu_db, raw_transcript="بدي دجاج")
    VoiceOrderDebugService.record_llm_prompt(
        abuu_db,
        system_prompt="smart prompt",
        messages=[{"role": "user", "content": "."}],
    )
    VoiceOrderDebugService.record_llm_raw(
        abuu_db,
        raw_response='{"reply":"هاي","action":"none","restaurant_id":null,"item_id":null,"order_confirmed":false}',
    )
    VoiceOrderDebugService.record_parsed(
        abuu_db,
        parsed={"action": "none", "reply": "هاي", "pipeline": "smart"},
        parse_status="ok",
    )
    abuu_db.commit()

    orders_before = abuu_db.execute(select(func.count()).select_from(CustomerOrder)).scalar_one()

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as main_db, patch(
        "app.abuu.services.voice_order_replay_service.WaiterDeepSeekClient.complete",
        return_value=type("R", (), {"text": '{"reply":"replay","action":"none"}', "fallback_used": False, "error": None})(),
    ):
        result = VoiceOrderReplayService.replay(
            abuu_db,
            main_db,
            order_request_id=request_id,
            from_step=4,
            dry_run=True,
        )

    orders_after = abuu_db.execute(select(func.count()).select_from(CustomerOrder)).scalar_one()
    assert orders_after == orders_before
    assert result["dry_run"] is True
    assert "replay" in result
    assert result["replay"]["5_parsed"]["parse_status"] == "ok"


def test_context_var_resolution(abuu_db, voice_debug_enabled):
    request_id = VoiceOrderDebugService.begin(
        abuu_db,
        customer_phone="+972509990103",
        message_id="msg-3",
        pipeline="agent",
    )
    set_debug_request_id(request_id)
    VoiceOrderDebugService.record_stt(abuu_db, raw_transcript="test")
    abuu_db.commit()
    row = abuu_db.get(AbuuVoiceOrderDebug, request_id)
    assert row is not None
    assert row.stt_raw_transcript == "test"
