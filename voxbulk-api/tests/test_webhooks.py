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


def test_telnyx_inbound_whatsapp_message_webhook(app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="WhatsApp Inbound Org")
        db.add(org)
        db.commit()
        org_id = org.id

    payload = {
        "data": {
            "event_type": "message.received",
            "payload": {
                "id": "msg-wa-inbound-001",
                "direction": "inbound",
                "type": "WHATSAPP",
                "from": {"phone_number": "+447700900123"},
                "to": [{"phone_number": "+442046203055"}],
                "body": {"type": "text", "text": {"body": "Hello from WhatsApp"}},
                "status": "received",
            },
        }
    }
    r = app_client.post("/telnyx/webhooks/messages", json=payload, headers={"X-Retover-Org-Id": org_id})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("channel") == "whatsapp"

    with get_sessionmaker()() as db:
        from app.models.whatsapp_log import WhatsAppLog
        from sqlalchemy import select

        row = db.execute(
            select(WhatsAppLog).where(WhatsAppLog.external_message_id == "msg-wa-inbound-001")
        ).scalar_one_or_none()
        assert row is not None
        assert row.body == "Hello from WhatsApp"
        assert row.direction == "inbound"


def test_telnyx_whatsapp_template_validation_rejects_numeric_name():
    from app.services.telnyx_messaging_service import TelnyxMessagingService

    err = TelnyxMessagingService.validate_whatsapp_template_ref("212", None)
    assert err
    assert "212" in err


def test_telnyx_message_finalized_delivery_failed(app_client):
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.models.whatsapp_log import WhatsAppLog

    with get_sessionmaker()() as db:
        org = Organisation(name="WA Delivery Fail Org")
        db.add(org)
        db.commit()
        org_id = org.id
        row = WhatsAppLog(
            org_id=org_id,
            provider="telnyx",
            external_message_id="msg-wa-out-001",
            status="queued",
            direction="outbound",
            to_number="+447954823445",
            from_number="+447822002055",
            body="[template:hello_world] test",
        )
        db.add(row)
        db.commit()

    payload = {
        "data": {
            "event_type": "message.finalized",
            "payload": {
                "id": "msg-wa-out-001",
                "direction": "outbound",
                "type": "WHATSAPP",
                "from": {"phone_number": "+447822002055"},
                "to": [{"phone_number": "+447954823445", "status": "delivery_failed"}],
                "errors": [
                    {
                        "code": "131026",
                        "title": "Template not found",
                        "detail": "The template name does not exist in the translation.",
                    }
                ],
            },
        }
    }
    r = app_client.post("/telnyx/webhooks/messages", json=payload, headers={"X-Retover-Org-Id": org_id})
    assert r.status_code == 200

    with get_sessionmaker()() as db:
        row = db.execute(
            select(WhatsAppLog).where(WhatsAppLog.external_message_id == "msg-wa-out-001")
        ).scalar_one()
        assert row.status == "delivery_failed"
        assert "template name does not exist" in str(row.body).lower()


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
