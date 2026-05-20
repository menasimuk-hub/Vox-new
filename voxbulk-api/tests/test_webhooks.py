from app.core.security import compute_gocardless_signature_hex


def test_telnyx_messages_webhook_probe(app_client):
    r = app_client.get("/telnyx/webhooks/messages")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_telnyx_inbound_message_webhook(app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="Inbound Test Org")
        db.add(org)
        db.commit()
        org_id = org.id

    payload = {
        "data": {
            "event_type": "message.received",
            "payload": {
                "id": "msg-test-001",
                "direction": "inbound",
                "type": "SMS",
                "from": {"phone_number": "+447700900123"},
                "to": [{"phone_number": "+442046203055"}],
                "text": "Meta verification code 123456",
                "status": "received",
            },
        }
    }
    r = app_client.post("/telnyx/webhooks/messages", json=payload, headers={"X-Retover-Org-Id": org_id})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("log_id")


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
