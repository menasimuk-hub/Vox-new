from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _mk_admin(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Billing Org")
        db.add(org)
        db.flush()
        admin = User(email="billadmin@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post("/auth/token", data={"username": "billadmin@example.com", "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, org_id


def test_payment_event_sends_only_once_for_failed_status(app_client):
    headers, org_id = _mk_admin(app_client)

    payload = {
        "provider": "internal",
        "external_event_id": "PAY_FAIL_1",
        "org_id": org_id,
        "client_email": "client@example.com",
        "status": "failed",
        "failure_reason": "declined",
        "variables": {"amount": "1000"},
    }

    with patch("app.services.product_email_triggers.TransactionalEmailService.send_templated_optional", return_value=(True, None)) as m:
        r1 = app_client.post("/admin/billing/payment-events", json=payload, headers=headers)
        r2 = app_client.post("/admin/billing/payment-events", json=payload, headers=headers)

    assert r1.status_code == 200
    assert r1.json()["sent"] is True
    assert r2.status_code == 200
    assert r2.json()["sent"] is False
    assert m.call_count == 1


def test_payment_event_does_not_send_when_not_failed(app_client):
    headers, org_id = _mk_admin(app_client)
    payload = {
        "provider": "internal",
        "external_event_id": "PAY_OK_1",
        "org_id": org_id,
        "client_email": "client@example.com",
        "status": "paid",
    }
    with patch("app.services.product_email_triggers.TransactionalEmailService.send_templated_optional", return_value=(True, None)) as m:
        r = app_client.post("/admin/billing/payment-events", json=payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["sent"] is False
    assert m.call_count == 0


def test_invoice_create_sends_only_once(app_client):
    headers, org_id = _mk_admin(app_client)
    payload = {
        "provider": "internal",
        "external_invoice_id": "INV_123",
        "org_id": org_id,
        "client_email": "client@example.com",
        "amount_gbp_pence": 2500,
        "currency": "GBP",
        "status": "issued",
    }
    with patch("app.services.product_email_triggers.TransactionalEmailService.send_templated_optional", return_value=(True, None)) as m:
        r1 = app_client.post("/admin/billing/invoices", json=payload, headers=headers)
        r2 = app_client.post("/admin/billing/invoices", json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["sent"] is True
    assert r2.status_code == 200
    assert r2.json()["sent"] is False
    assert m.call_count == 1

