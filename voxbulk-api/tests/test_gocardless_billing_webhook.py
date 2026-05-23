from __future__ import annotations

import json
from unittest.mock import patch

from app.core.database import get_sessionmaker
from app.core.security import compute_gocardless_signature_hex, hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.payment_event import PaymentEvent
from app.models.user import User
from sqlalchemy import select


def _billing_super_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="GC Billing Org")
        db.add(org)
        db.flush()
        admin = User(
            email="gc_bill@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "gc_bill@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, org_id


def _signed_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_gocardless_payment_failed_webhook_maps_and_emails_once(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_PAY_FAIL_1",
                "resource_type": "payments",
                "action": "failed",
                "metadata": {"org_id": org_id, "client_email": "tenant@example.com"},
                "details": {"description": "Insufficient funds", "cause": "bank_declined"},
                "links": {"payment": "PM_QQ_1"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ) as send_mock:
        r1 = app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        assert r1.status_code == 200
        r2 = app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        assert r2.status_code == 200

    assert send_mock.call_count == 1

    with get_sessionmaker()() as db:
        row = db.execute(select(PaymentEvent).where(PaymentEvent.external_event_id == "EV_PAY_FAIL_1")).scalar_one()
        assert row.provider == "gocardless"
        assert row.status == "failed"
        assert row.emailed_at is not None


def test_gocardless_duplicate_payment_webhook_single_email(app_client):
    """Same webhook POST twice → one WebhookEvent row; celery runs once → one email."""
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_DUP_PAY",
                "resource_type": "payments",
                "action": "failed",
                "metadata": {"org_id": org_id, "client_email": "dup@example.com"},
                "links": {"payment": "PM_DUP"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ) as send_mock:
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})

    assert send_mock.call_count == 1


def test_gocardless_invoice_created_triggers_new_invoice_hook(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_INV_HOOK",
                "resource_type": "invoices",
                "action": "invoice_created",
                "metadata": {
                    "org_id": org_id,
                    "client_email": "invoice@example.com",
                    "amount_gbp_pence": 1234,
                    "currency": "GBP",
                },
                "links": {"invoice": "INV_GC_900"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ) as send_mock:
        r = app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        assert r.status_code == 200

    keys = [c.kwargs.get("template_key") for c in send_mock.call_args_list]
    assert "new_invoice" in keys


def test_gocardless_skip_missing_metadata_no_email(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_SKIP_META",
                "resource_type": "payments",
                "action": "failed",
                "metadata": {"org_id": org_id},
                "links": {"payment": "PM_X"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ) as send_mock:
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})

    assert send_mock.call_count == 0


def test_admin_list_recent_payment_events(app_client):
    headers, org_id = _billing_super_headers(app_client)
    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ):
        app_client.post(
            "/admin/billing/payment-events",
            json={
                "provider": "internal",
                "external_event_id": "ADM_LIST_1",
                "org_id": org_id,
                "client_email": "z@example.com",
                "status": "failed",
            },
            headers=headers,
        )
    lst = app_client.get("/admin/billing/payment-events/recent?limit=5", headers=headers)
    assert lst.status_code == 200
    assert isinstance(lst.json(), list)
    assert any(x.get("external_event_id") == "ADM_LIST_1" for x in lst.json())


def test_invoice_duplicate_webhook_does_not_resend(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_INV_IDEM",
                "resource_type": "invoices",
                "action": "created",
                "metadata": {"org_id": org_id, "client_email": "idem@example.com"},
                "links": {"invoice": "INV_IDEM_Z"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ) as send_mock:
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})

    new_invoice_calls = [c for c in send_mock.call_args_list if c.kwargs.get("template_key") == "new_invoice"]
    assert len(new_invoice_calls) == 1


def test_gocardless_webhook_uses_provider_settings_secret(app_client):
    headers, org_id = _billing_super_headers(app_client)
    saved = app_client.put(
        "/admin/integrations/gocardless",
        json={
            "is_enabled": True,
            "config": {
                "access_token": "sandbox-token",
                "environment": "sandbox",
                "webhook_secret": "provider-gc-secret",
                "webhook_url": "http://testserver/webhooks/gocardless",
            },
        },
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["configured"] is True

    body_dict = {
        "events": [
            {
                "id": "EV_PROVIDER_SECRET",
                "resource_type": "payments",
                "action": "failed",
                "metadata": {"org_id": org_id, "client_email": "provider-secret@example.com"},
                "links": {"payment": "PM_PROVIDER_SECRET"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="provider-gc-secret", body=raw)
    with patch(
        "app.services.product_email_triggers.TransactionalEmailService.send_templated_optional",
        return_value=(True, None),
    ):
        res = app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
    assert res.status_code == 200


def test_gocardless_payment_confirmed_creates_invoice(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_PAY_OK_1",
                "resource_type": "payments",
                "action": "confirmed",
                "metadata": {
                    "org_id": org_id,
                    "client_email": "tenant@example.com",
                    "amount_gbp_pence": 9900,
                },
                "links": {"payment": "PM_RECUR_1", "subscription": "SB_RECUR_1"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
        return_value=(True, None),
    ):
        r = app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        assert r.status_code == 200

    with get_sessionmaker()() as db:
        inv = db.execute(
            select(BillingInvoice).where(BillingInvoice.external_invoice_id == "payment:PM_RECUR_1")
        ).scalar_one()
        assert inv.org_id == org_id
        assert inv.provider == "gocardless"
        assert inv.status == "paid"


def test_gocardless_payment_confirmed_idempotent(app_client):
    _, org_id = _billing_super_headers(app_client)
    body_dict = {
        "events": [
            {
                "id": "EV_PAY_IDEM",
                "resource_type": "payments",
                "action": "confirmed",
                "metadata": {
                    "org_id": org_id,
                    "client_email": "dup@example.com",
                    "amount_gbp_pence": 9900,
                },
                "links": {"payment": "PM_IDEM", "subscription": "SB_IDEM"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
        return_value=(True, None),
    ) as send_mock:
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})

    assert send_mock.call_count == 1
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(BillingInvoice).where(BillingInvoice.external_invoice_id == "payment:PM_IDEM")
        ).scalars().all()
        assert len(rows) == 1


def test_gocardless_payment_confirmed_skips_duplicate_initial(app_client):
    _, org_id = _billing_super_headers(app_client)
    amount = 9900
    with get_sessionmaker()() as db:
        db.add(
            BillingInvoice(
                org_id=org_id,
                provider="gocardless",
                external_invoice_id="sub:SB_DUP_INIT:initial",
                client_email="tenant@example.com",
                amount_gbp_pence=amount,
                subtotal_pence=amount,
                currency="GBP",
                status="paid",
            )
        )
        db.commit()

    body_dict = {
        "events": [
            {
                "id": "EV_PAY_DUP_INIT",
                "resource_type": "payments",
                "action": "confirmed",
                "metadata": {
                    "org_id": org_id,
                    "client_email": "tenant@example.com",
                    "amount_gbp_pence": amount,
                },
                "links": {"payment": "PM_DUP_INIT", "subscription": "SB_DUP_INIT"},
            }
        ]
    }
    raw = _signed_body(body_dict)
    sig = compute_gocardless_signature_hex(secret="gc-test", body=raw)

    with patch(
        "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
        return_value=(True, None),
    ) as send_mock:
        app_client.post("/webhooks/gocardless", content=raw, headers={"Webhook-Signature": sig})

    assert send_mock.call_count == 0
    with get_sessionmaker()() as db:
        assert (
            db.execute(
                select(BillingInvoice).where(BillingInvoice.external_invoice_id == "payment:PM_DUP_INIT")
            ).scalar_one_or_none()
            is None
        )
