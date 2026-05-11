from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.providers.openai_service import OpenAIResponse


def _headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Telnyx Voice Org")
        db.add(org)
        db.flush()
        user = User(email="telnyx_voice@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        email = user.email
    token = app_client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _save_voice_stack(app_client, headers):
    telnyx = app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "KEYtelnyx",
                "connection_id": "conn-123",
                "default_outbound_number": "+442071111111",
                "fallback_caller_id": "+442072222222",
                "voice_webhook_url": "http://testserver/telnyx/webhooks/voice",
                "status_callback_url": "http://testserver/telnyx/webhooks/status",
                "verified_number_webhook_url": "http://testserver/telnyx/webhooks/verified-numbers",
                "media_stream_url": "wss://testserver/telnyx/media-stream",
            },
        },
        headers=headers,
    )
    assert telnyx.status_code == 200
    assert telnyx.json()["configured"] is True
    azure = app_client.put(
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
    assert azure.status_code == 200
    openai = app_client.put(
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
    assert openai.status_code == 200


def test_telnyx_settings_and_verified_caller_id_flow(app_client, monkeypatch):
    headers, _org_id = _headers(app_client)
    _save_voice_stack(app_client, headers)

    saved = app_client.put("/auth/me/phone", json={"phone_number": "+447700900456"}, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["phone_e164"] == "+447700900456"
    assert saved.json()["verification_status"] == "unverified"

    def fake_verified_number_request(**kwargs):
        assert kwargs["api_key"] == "KEYtelnyx"
        assert kwargs["phone_number"] == "+447700900456"
        return {"data": {"id": "VN123", "verification_id": "VER123", "status": "pending", "verification_code": "123456"}}

    monkeypatch.setattr(
        "app.services.telnyx_voice_service.TelnyxCallerIdService._create_verified_number_request",
        staticmethod(fake_verified_number_request),
    )
    verify = app_client.post("/auth/me/phone/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["telnyx_verification_id"] == "VER123"

    cb = app_client.post(
        "/telnyx/webhooks/verified-numbers",
        json={"data": {"payload": {"verification_id": "VER123", "verified_number_id": "VN123", "phone_number": "+447700900456", "status": "verified"}}},
    )
    assert cb.status_code == 200

    refreshed = app_client.get("/auth/me/phone", headers=headers)
    assert refreshed.json()["verification_status"] == "verified"
    assert refreshed.json()["telnyx_verified_number_id"] == "VN123"

    def fake_call(**kwargs):
        assert kwargs["api_key"] == "KEYtelnyx"
        assert kwargs["from_number"] == "+447700900456"
        assert kwargs["media_stream_url"] == "wss://testserver/telnyx/media-stream"
        return {"data": {"call_control_id": "call-123", "status": "queued"}}

    monkeypatch.setattr("app.services.telnyx_voice_service.TelnyxVoiceAdapter._create_call", staticmethod(fake_call))
    call = app_client.post("/calls/start", json={"to_number": "+447700900123", "llm_prompt": "Recover an appointment"}, headers=headers)
    assert call.status_code == 200
    assert call.json()["ok"] is True
    assert call.json()["log"]["provider"] == "telnyx"
    assert call.json()["log"]["from_number"] == "+447700900456"
    assert call.json()["log"]["llm_prompt"] == "Recover an appointment"


def test_telnyx_unverified_user_falls_back_to_admin_caller_id(app_client, monkeypatch):
    headers, _org_id = _headers(app_client)
    _save_voice_stack(app_client, headers)
    app_client.put("/auth/me/phone", json={"phone_number": "+447700900789"}, headers=headers)

    def fake_call(**kwargs):
        assert kwargs["from_number"] == "+442072222222"
        return {"data": {"call_control_id": "call-fallback", "status": "queued"}}

    monkeypatch.setattr("app.services.telnyx_voice_service.TelnyxVoiceAdapter._create_call", staticmethod(fake_call))
    call = app_client.post("/calls/start", json={"to_number": "+447700900123"}, headers=headers)
    assert call.status_code == 200
    assert call.json()["log"]["from_number"] == "+442072222222"


def test_telnyx_media_stream_appends_transcript(app_client, monkeypatch):
    headers, _org_id = _headers(app_client)
    _save_voice_stack(app_client, headers)

    def fake_call(**kwargs):
        return {"data": {"call_control_id": "call-stream", "status": "queued"}}

    monkeypatch.setattr("app.services.telnyx_voice_service.TelnyxVoiceAdapter._create_call", staticmethod(fake_call))
    call = app_client.post("/calls/start", json={"to_number": "+447700900123"}, headers=headers)
    assert call.status_code == 200

    monkeypatch.setattr(
        "app.services.agents.manager.OpenAIProviderService.complete",
        staticmethod(lambda db, system_prompt, messages, model=None, tools=None: OpenAIResponse(assistant_text="We can help you rebook tomorrow.")),
    )
    monkeypatch.setattr(
        "app.services.agents.manager.AzureSpeechProviderService.synthesize_text",
        staticmethod(lambda db, text: b"audio-bytes"),
    )

    with app_client.websocket_connect("/telnyx/media-stream") as ws:
        ws.send_json({"call_control_id": "call-stream", "transcript": "Can I move my appointment?"})
        msg = ws.receive_json()
        assert msg["type"] == "agent_response"
        assert msg["text"] == "We can help you rebook tomorrow."

    logs = app_client.get("/calls", headers=headers)
    row = next(x for x in logs.json() if x["external_call_id"] == "call-stream")
    assert "Can I move my appointment?" in row["transcript_text"]
    assert "We can help you rebook tomorrow." in row["transcript_text"]
