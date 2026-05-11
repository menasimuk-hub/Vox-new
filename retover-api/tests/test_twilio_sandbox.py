from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import compute_twilio_signature, hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Twilio Sandbox Org")
        db.add(org)
        db.flush()
        user = User(email="twilio_sandbox@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
    token = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _save_twilio(app_client, headers):
    res = app_client.put(
        "/admin/integrations/twilio",
        json={
            "is_enabled": True,
            "config": {
                "account_sid": "ACsandbox",
                "auth_token": "twilio-test-auth-token",
                "whatsapp_from": "whatsapp:+14155238886",
                "from_number": "+15005550006",
                "twiml_url": "https://example.com/twiml.xml",
                "status_callback_url": "http://testserver/twilio/webhooks/calls",
                "whatsapp_webhook_url": "http://testserver/twilio/webhooks/whatsapp",
                "sandbox_mode": True,
            },
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["configured"] is True


def test_twilio_outbound_whatsapp_and_call_use_provider_settings(app_client, monkeypatch):
    headers, _org_id = _headers(app_client)
    _save_twilio(app_client, headers)

    def fake_message(**kwargs):
        assert kwargs["account_sid"] == "ACsandbox"
        assert kwargs["api_secret"] == "twilio-test-auth-token"
        assert kwargs["from_number"] == "whatsapp:+14155238886"
        assert kwargs["media_urls"] == ["https://example.com/a.png"]
        return {"sid": "SMsandbox", "status": "queued"}

    monkeypatch.setattr("app.services.twilio_service.TwilioWhatsAppAdapter._create_message", staticmethod(fake_message))

    wa = app_client.post(
        "/whatsapp/send",
        json={"to_number": "+447700900123", "body": "Sandbox test", "media_urls": ["https://example.com/a.png"]},
        headers=headers,
    )
    assert wa.status_code == 200
    assert wa.json()["ok"] is True
    assert wa.json()["log"]["external_message_id"] == "SMsandbox"


def test_twilio_whatsapp_sandbox_webhook_logs_inbound_message(app_client):
    headers, org_id = _headers(app_client)
    _save_twilio(app_client, headers)

    url = "http://testserver/twilio/webhooks/whatsapp"
    form = {
        "From": "whatsapp:+447700900123",
        "To": "whatsapp:+14155238886",
        "Body": "JOIN sandbox",
        "MessageSid": "SMinbound",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/1",
        "MediaContentType0": "image/png",
    }
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params=form)
    res = app_client.post(url, data=form, headers={"X-Twilio-Signature": sig, "X-Retover-Org-Id": org_id})
    assert res.status_code == 200
    log_id = res.json()["log_id"]

    logs = app_client.get("/whatsapp", headers=headers)
    assert logs.status_code == 200
    row = next(x for x in logs.json() if x["id"] == log_id)
    assert row["direction"] == "inbound"
    assert row["from_number"] == "whatsapp:+447700900123"
    assert row["body"] == "JOIN sandbox"


def test_twilio_call_webhook_updates_call_log(app_client):
    headers, org_id = _headers(app_client)
    _save_twilio(app_client, headers)

    created = app_client.post(
        "/calls",
        json={"provider": "twilio", "external_call_id": "CAwebhook", "direction": "outbound", "status": "queued"},
        headers=headers,
    )
    assert created.status_code == 200

    url = "http://testserver/twilio/webhooks/calls"
    form = {
        "CallSid": "CAwebhook",
        "CallStatus": "completed",
        "From": "+15005550006",
        "To": "+447700900123",
        "RecordingUrl": "https://api.twilio.com/recording.wav",
    }
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params=form)
    res = app_client.post(url, data=form, headers={"X-Twilio-Signature": sig, "X-Retover-Org-Id": org_id})
    assert res.status_code == 200

    logs = app_client.get("/calls", headers=headers)
    row = next(x for x in logs.json() if x["external_call_id"] == "CAwebhook")
    assert row["status"] == "completed"
    assert row["recording_url"] == "https://api.twilio.com/recording.wav"


