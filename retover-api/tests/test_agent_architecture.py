from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.agent import AgentAssignment, AgentDefinition
from app.models.category import Category
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.patient import Patient
from app.models.user import User
from app.services.agents.manager import AgentManager
from app.services.providers.azure_speech import AzureSpeechProviderService
from app.services.providers.openai_service import OpenAIResponse
from app.services.voice_agent_service import AzureSpeechService


def _headers(app_client):
    with get_sessionmaker()() as db:
        cat = Category(slug="dental", name="Dental")
        db.add(cat)
        db.flush()
        org = Organisation(name="Agent Org", category_id=cat.id)
        db.add(org)
        db.flush()
        user = User(email="agent_admin@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.add(Patient(org_id=org.id, first_name="Jane", last_name="Patient", phone_e164="+447700900001"))
        db.commit()
        org_id = org.id
        category_id = cat.id
        email = user.email
    token = app_client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id, category_id


def _save_providers(app_client, headers):
    app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "KEYtelnyx",
                "connection_id": "conn-123",
                "default_outbound_number": "+442071111111",
                "fallback_caller_id": "+442072222222",
                "media_stream_url": "wss://testserver/telnyx/media-stream",
            },
        },
        headers=headers,
    )
    app_client.put(
        "/admin/integrations/openai",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "openai-key",
                "default_model": "gpt-realtime-1.5",
                "realtime_model": "gpt-realtime-1.5",
                "temperature": 0.4,
                "max_output_tokens": 500,
            },
        },
        headers=headers,
    )
    app_client.put(
        "/admin/integrations/azure_speech",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "azure-key",
                "region": "uksouth",
                "default_voice_id": "en-GB-AbbiNeural",
                "stt_enabled": False,
                "tts_enabled": True,
            },
        },
        headers=headers,
    )


def test_agent_crud_and_assignment_resolution(app_client):
    headers, org_id, category_id = _headers(app_client)
    listed = app_client.get("/admin/agents", headers=headers)
    assert listed.status_code == 200
    default = next(a for a in listed.json()["agents"] if a["slug"] == "british-clinic-assistant")

    created = app_client.post(
        "/admin/agents",
        json={
            "name": "Custom Clinic Agent",
            "slug": "custom-clinic-agent",
            "system_prompt": "You are a custom clinic assistant.",
            "allow_lookup_tool": True,
        },
        headers=headers,
    )
    assert created.status_code == 200
    custom_id = created.json()["id"]

    org_assign = app_client.put(f"/admin/agents/assignments/organisation/{org_id}", json={"agent_id": custom_id}, headers=headers)
    assert org_assign.status_code == 200
    category_assign = app_client.put(f"/admin/agents/assignments/business-type/{category_id}", json={"agent_id": default["id"]}, headers=headers)
    assert category_assign.status_code == 200

    with get_sessionmaker()() as db:
        resolved = AgentManager.resolve_agent(db, org_id=org_id)
    assert resolved.id == custom_id


def test_agent_preview_and_tool_lookup(app_client, monkeypatch):
    headers, org_id, _category_id = _headers(app_client)
    _save_providers(app_client, headers)

    def fake_complete(db, *, system_prompt, messages, model=None, tools=None, max_tokens=None, temperature=None):
        assert "British Clinic Assistant" in system_prompt
        assert tools
        return OpenAIResponse(assistant_text="Of course, I can help with that.", usage={"total_tokens": 10})

    monkeypatch.setattr("app.services.agents.manager.OpenAIProviderService.complete", staticmethod(fake_complete))
    preview = app_client.post(
        "/admin/agents/preview",
        json={"org_id": org_id, "input": "Can I move my appointment?"},
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.json()["assistant_text"] == "Of course, I can help with that."


def test_openai_integration_rejects_incomplete_settings(app_client, monkeypatch):
    headers, _org_id, _category_id = _headers(app_client)
    bad = app_client.put(
        "/admin/integrations/openai",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "openai-key",
                "default_model": "",
                "realtime_model": "",
                "temperature": "hot",
                "max_output_tokens": 0,
            },
        },
        headers=headers,
    )
    assert bad.status_code == 400
    assert "default_model" in bad.json()["detail"]
    assert "realtime_model" in bad.json()["detail"]
    assert "temperature" in bad.json()["detail"]
    assert "max_output_tokens" in bad.json()["detail"]

    good = app_client.put(
        "/admin/integrations/openai",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "openai-key",
                "default_model": "gpt-realtime-1.5",
                "realtime_model": "gpt-realtime-1.5",
                "temperature": "0.4",
                "max_output_tokens": "500",
            },
        },
        headers=headers,
    )
    assert good.status_code == 200
    assert good.json()["configured"] is True

    def fake_test_completion_raw(db, *, prompt=None):
        assert prompt == "Say hello in one short sentence."
        return {
            "ok": True,
            "status_code": 200,
            "prompt": prompt,
            "assistant_text": "Hello, I can help you today.",
            "usage": {"total_tokens": 12},
            "diagnostics": {
                "base_url": "https://api.openai.com",
                "default_model": "gpt-realtime-1.5",
                "endpoint_path": "/v1/chat/completions",
                "api_key_length": len("openai-key"),
            },
            "openai_payload": {"choices": [{"message": {"content": "Hello, I can help you today."}}]},
            "persisted": False,
        }

    monkeypatch.setattr("app.routers.admin.OpenAIProviderService.test_completion_raw", staticmethod(fake_test_completion_raw))
    smoke = app_client.post("/admin/integrations/openai/test", headers=headers)
    assert smoke.status_code == 200
    assert smoke.json()["ok"] is True
    assert "Hello" in smoke.json()["assistant_text"]
    assert smoke.json()["persisted"] is False


def test_azure_speech_validation_and_tts_smoke_route(app_client, monkeypatch):
    headers, _org_id, _category_id = _headers(app_client)
    bad = app_client.put(
        "/admin/integrations/azure_speech",
        json={"is_enabled": True, "config": {"api_key": "azure-key", "region": "", "tts_enabled": True, "default_voice_id": ""}},
        headers=headers,
    )
    assert bad.status_code == 400
    assert "region" in bad.json()["detail"]
    assert "default_voice_id" in bad.json()["detail"]

    tts_disabled = app_client.put(
        "/admin/integrations/azure_speech",
        json={"is_enabled": True, "config": {"api_key": "azure-key", "region": "uksouth", "tts_enabled": False, "stt_enabled": False}},
        headers=headers,
    )
    assert tts_disabled.status_code == 200
    assert tts_disabled.json()["configured"] is True

    good = app_client.put(
        "/admin/integrations/azure_speech",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "azure-key",
                "region": "northeurope",
                "default_voice_id": "en-GB-AbbiNeural",
                "tts_enabled": True,
                "stt_enabled": False,
            },
        },
        headers=headers,
    )
    assert good.status_code == 200
    assert good.json()["configured"] is True

    def fake_test_tts(db, *, text=None):
        assert text == "Hello, this is your clinic assistant speaking."
        return {
            "ok": True,
            "phrase": text,
            "audio_bytes": 5,
            "diagnostics": {
                "region": "northeurope",
                "api_key_length": len("azure-key"),
                "rest_equivalent": {"url": "https://northeurope.tts.speech.microsoft.com/cognitiveservices/v1"},
            },
            "persisted_audio": False,
        }

    monkeypatch.setattr("app.routers.admin.AzureSpeechProviderService.test_tts", staticmethod(fake_test_tts))
    smoke = app_client.post("/admin/integrations/azure_speech/test-tts", headers=headers)
    assert smoke.status_code == 200
    assert smoke.json()["ok"] is True
    assert smoke.json()["audio_bytes"] == 5
    assert smoke.json()["persisted_audio"] is False
    assert smoke.json()["diagnostics"]["region"] == "northeurope"
    assert smoke.json()["diagnostics"]["api_key_length"] == len("azure-key")
    assert smoke.json()["diagnostics"]["rest_equivalent"]["url"] == "https://northeurope.tts.speech.microsoft.com/cognitiveservices/v1"

    def fake_cancelled_test_tts(db, *, text=None):
        return {
            "ok": False,
            "phrase": text,
            "error_code": "ConnectionFailure",
            "error_details": "404 Not Found",
            "cancellation_reason": "Error",
            "diagnostics": {
                "region": "northeurope",
                "api_key_length": len("azure-key"),
            },
            "persisted_audio": False,
        }

    monkeypatch.setattr("app.routers.admin.AzureSpeechProviderService.test_tts", staticmethod(fake_cancelled_test_tts))
    cancelled = app_client.post("/admin/integrations/azure_speech/test-tts", headers=headers)
    assert cancelled.status_code == 502
    assert cancelled.json()["detail"]["error_code"] == "ConnectionFailure"
    assert cancelled.json()["detail"]["error_details"] == "404 Not Found"


def test_demo_agent_call_uses_agent_pipeline_without_telnyx(app_client, monkeypatch):
    headers, org_id, _category_id = _headers(app_client)
    _save_providers(app_client, headers)
    created = app_client.post(
        "/admin/agents",
        json={
            "name": "Vox Sales",
            "slug": "vox-sales",
            "system_prompt": "You are Vox Sales, a helpful sales voice assistant.",
            "default_model": "gpt-test",
            "use_azure_tts": True,
        },
        headers=headers,
    )
    assert created.status_code == 200

    def fake_complete(db, *, system_prompt, messages, model=None, tools=None, max_tokens=None, temperature=None):
        assert "Vox Sales" in system_prompt
        assert model == "gpt-4o-mini"
        assert max_tokens == 80
        assert temperature == 0.45
        assert messages[-1].content == "Can I speak to sales?"
        return OpenAIResponse(assistant_text="Of course, I can help with sales.", usage={"total_tokens": 9})

    def fake_tts(db, *, text, voice_id=None, output_format="telephony", use_ssml=True, speaking_rate=None):
        assert text == "Of course, I can help with sales."
        assert voice_id == "en-GB-RyanNeural"
        assert output_format == "browser_fast"
        assert use_ssml is True
        assert speaking_rate == "normal"
        return {"ok": True, "audio_data": b"wav-bytes", "audio_bytes": 9, "diagnostics": {"region": "northeurope"}}

    monkeypatch.setattr("app.services.agents.manager.OpenAIProviderService.complete", staticmethod(fake_complete))
    monkeypatch.setattr("app.routers.demo.AzureSpeechProviderService.synthesize_text_result", staticmethod(fake_tts))

    demo = app_client.post(
        "/demo/agent-call",
        json={"agent_slug": "vox-sales", "input": "Can I speak to sales?", "org_id": org_id},
        headers=headers,
    )
    assert demo.status_code == 200
    body = demo.json()
    assert body["ok"] is True
    assert body["agent_slug"] == "vox-sales"
    assert body["user_text"] == "Can I speak to sales?"
    assert body["agent_text"] == "Of course, I can help with sales."
    assert body["audio_b64"]
    assert body["audio_mime"] == "audio/mpeg"
    assert body["voice"]["voice_id"] == "en-GB-RyanNeural"
    assert body["voice"]["output_format"] == "audio-24khz-160kbitrate-mono-mp3"
    assert body["timings"]["openai_ms"] >= 0

    admin_demo = app_client.post(
        "/admin/demo/agent-call",
        json={"agent_slug": "vox-sales", "input": "Can I speak to sales?", "org_id": org_id},
        headers=headers,
    )
    assert admin_demo.status_code == 200
    assert admin_demo.json()["agent_slug"] == "vox-sales"


def test_azure_provider_accepts_browser_tts_options(monkeypatch):
    def fake_base(db, *, text, voice_id=None, output_format="telephony", use_ssml=True, speaking_rate=None):
        assert text == "Hello"
        assert voice_id == "en-GB-RyanNeural"
        assert output_format == "browser"
        assert use_ssml is True
        assert speaking_rate == "slightly_fast"
        return {"ok": True, "audio_data": b"audio", "audio_bytes": 5}

    monkeypatch.setattr(AzureSpeechService, "synthesize_text_result", staticmethod(fake_base))
    result = AzureSpeechProviderService.synthesize_text_result(
        None,
        text="Hello",
        voice_id="en-GB-RyanNeural",
        output_format="browser",
        use_ssml=True,
        speaking_rate="slightly_fast",
    )
    assert result["ok"] is True


def test_demo_agent_call_streams_text_and_audio_chunks(app_client, monkeypatch):
    headers, org_id, _category_id = _headers(app_client)
    _save_providers(app_client, headers)
    created = app_client.post(
        "/admin/agents",
        json={
            "name": "Vox Sales",
            "slug": "vox-sales",
            "system_prompt": "You are Vox Sales, a helpful sales voice assistant.",
            "default_model": "gpt-test",
            "use_azure_tts": True,
        },
        headers=headers,
    )
    assert created.status_code == 200

    def fake_stream_complete(db, *, system_prompt, messages, model=None, tools=None, max_tokens=None, temperature=None):
        assert "Vox Sales" in system_prompt
        assert model == "gpt-4o-mini"
        assert max_tokens == 80
        assert messages[-1].content == "Hello"
        yield "Hello there. "
        yield "How can I help?"

    def fake_chunk_tts(db, *, text, voice_id=None, output_format="browser_fast", speaking_rate=None):
        assert voice_id == "en-GB-RyanNeural"
        assert output_format == "browser_fast"
        assert speaking_rate == "normal"
        return {"ok": True, "audio_data": f"audio:{text}".encode(), "audio_bytes": len(text), "timings": {"azure_provider_total_ms": 1}}

    monkeypatch.setattr("app.routers.demo.OpenAIProviderService.stream_complete", staticmethod(fake_stream_complete))
    monkeypatch.setattr("app.routers.demo.AzureSpeechProviderService.synthesize_demo_chunk_result", staticmethod(fake_chunk_tts))

    response = app_client.post(
        "/admin/demo/agent-call/stream",
        json={"agent_slug": "vox-sales", "input": "Hello", "org_id": org_id},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.text
    assert "event: transcript_received" in body
    assert "event: llm_text_delta" in body
    assert "event: tts_audio_ready" in body
    assert "event: done" in body
    assert "Hello there. How can I help?" in body


def test_calls_start_accepts_agent_override_and_stream_uses_manager(app_client, monkeypatch):
    headers, _org_id, _category_id = _headers(app_client)
    _save_providers(app_client, headers)
    created = app_client.post(
        "/admin/agents",
        json={"name": "Override Agent", "slug": "override-agent", "system_prompt": "Override prompt", "default_model": "gpt-test"},
        headers=headers,
    )
    assert created.status_code == 200
    agent_id = created.json()["id"]

    def fake_call(**kwargs):
        return {"data": {"call_control_id": "agent-call-1", "status": "queued"}}

    monkeypatch.setattr("app.services.telnyx_voice_service.TelnyxVoiceAdapter._create_call", staticmethod(fake_call))
    call = app_client.post("/calls/start", json={"to_number": "+447700900123", "agent_id": agent_id}, headers=headers)
    assert call.status_code == 200
    assert call.json()["log"]["media_stream_id"] == agent_id

    def fake_complete(db, *, system_prompt, messages, model=None, tools=None, max_tokens=None, temperature=None):
        assert "Override prompt" in system_prompt
        assert model == "gpt-test"
        return OpenAIResponse(assistant_text="Let's look at that appointment.", usage={"total_tokens": 12})

    monkeypatch.setattr("app.services.agents.manager.OpenAIProviderService.complete", staticmethod(fake_complete))
    monkeypatch.setattr("app.services.agents.manager.AzureSpeechProviderService.synthesize_text", staticmethod(lambda db, text: b"audio"))

    with app_client.websocket_connect("/telnyx/media-stream") as ws:
        ws.send_json({"call_control_id": "agent-call-1", "transcript": "I need to rebook"})
        msg = ws.receive_json()
        assert msg["agent_id"] == agent_id
        assert msg["text"] == "Let's look at that appointment."

    logs = app_client.get("/calls", headers=headers)
    row = next(x for x in logs.json() if x["external_call_id"] == "agent-call-1")
    assert "I need to rebook" in row["transcript_text"]
    assert "Let's look at that appointment." in row["transcript_text"]
