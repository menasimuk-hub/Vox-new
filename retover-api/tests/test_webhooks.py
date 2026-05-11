from app.core.security import compute_gocardless_signature_hex, compute_twilio_signature


def test_webhook_rejects_invalid_signature(app_client):
    r = app_client.post("/webhooks/twilio", data={"foo": "bar"}, headers={"X-Twilio-Signature": "bad"})
    assert r.status_code == 401


def test_webhook_accepts_valid_signature(app_client):
    url = "http://testserver/webhooks/twilio"
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params={"foo": "bar"})
    r = app_client.post("/webhooks/twilio", data={"foo": "bar"}, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200


def test_gocardless_webhook_signature(app_client):
    body = b"{\"events\":[{\"id\":\"EV123\"}]}"
    sig = compute_gocardless_signature_hex(secret="gc-test", body=body)
    r_ok = app_client.post("/webhooks/gocardless", content=body, headers={"Webhook-Signature": sig})
    assert r_ok.status_code == 200

    r_bad = app_client.post("/webhooks/gocardless", content=body, headers={"Webhook-Signature": "deadbeef"})
    assert r_bad.status_code == 401


def test_gocardless_duplicate_external_event_id_is_ignored(app_client):
    body = b"{\"events\":[{\"id\":\"EV999\"}]}"
    sig = compute_gocardless_signature_hex(secret="gc-test", body=body)
    r1 = app_client.post("/webhooks/gocardless", content=body, headers={"Webhook-Signature": sig})
    assert r1.status_code == 200
    r2 = app_client.post("/webhooks/gocardless", content=body, headers={"Webhook-Signature": sig})
    assert r2.status_code == 200

    from app.core.database import get_sessionmaker
    from app.models.webhook_event import WebhookEvent
    from sqlalchemy import func, select

    with get_sessionmaker()() as db:
        cnt = db.execute(
            select(func.count()).select_from(WebhookEvent).where(WebhookEvent.provider == "gocardless")
        ).scalar_one()
    assert int(cnt) == 1

