from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.dentally_appointment import DentallyAppointment
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.recovery_job import RecoveryJob
from app.models.user import User
from app.models.webhook_event import WebhookEvent
from sqlalchemy import select


def _seed_user(app_client, *, email: str = "phase7_user@example.com", superuser: bool = False):
    with get_sessionmaker()() as db:
        org = Organisation(name="Phase 7 Clinic")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True, is_superuser=superuser)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        user_id = user.id

    token = app_client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id


def test_gocardless_sandbox_redirect_start_and_complete(app_client, monkeypatch):
    headers, org_id, _user_id = _seed_user(app_client, email="phase7_gc@example.com", superuser=True)

    admin_save = app_client.put(
        "/admin/integrations/gocardless",
        json={
            "is_enabled": True,
            "config": {
                "access_token": "sandbox-token",
                "environment": "sandbox",
                "webhook_secret": "gc-test",
                "webhook_url": "http://testserver/webhooks/gocardless",
                "success_redirect_url": "http://localhost:5175/packages?billing=success",
                "cancel_redirect_url": "http://localhost:5175/packages?billing=cancelled",
            },
        },
        headers=headers,
    )
    assert admin_save.status_code == 200
    assert admin_save.json()["configured"] is True

    class _FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            if url.endswith("/redirect_flows"):
                return _FakeResponse({"redirect_flows": {"id": "RE_PHASE7", "redirect_url": "https://pay-sandbox.example/flow"}})
            if url.endswith("/redirect_flows/RE_PHASE7/actions/complete"):
                return _FakeResponse({"redirect_flows": {"links": {"mandate": "MD_PHASE7", "customer": "CU_PHASE7"}}})
            if url.endswith("/subscriptions"):
                return _FakeResponse({"subscriptions": {"id": "SB_PHASE7"}})
            raise AssertionError(f"unexpected GoCardless URL: {url}")

    monkeypatch.setattr("app.services.gocardless_service.httpx.Client", _FakeClient)

    plans = app_client.get("/billing/plans").json()
    start = app_client.post("/billing/subscription/gocardless/start", json={"plan_id": plans[0]["id"]}, headers=headers)
    assert start.status_code == 200
    assert start.json()["environment"] == "sandbox"
    assert start.json()["authorization_url"] == "https://pay-sandbox.example/flow"

    with patch(
        "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
        return_value=(True, None),
    ):
        complete = app_client.post(
            "/billing/subscription/gocardless/complete",
            json={"redirect_flow_id": "RE_PHASE7"},
            headers=headers,
        )
    assert complete.status_code == 200
    body = complete.json()
    assert body["status"] == "completed"
    assert body["subscription"]["payment_provider"] == "gocardless"
    assert body["subscription"]["payment_mode"] == "sandbox"
    assert body["subscription"]["external_subscription_id"] == "SB_PHASE7"

    with get_sessionmaker()() as db:
        inv = db.execute(
            select(BillingInvoice).where(BillingInvoice.external_invoice_id == "sub:SB_PHASE7:initial")
        ).scalar_one()
        assert inv.org_id == org_id
        assert inv.provider == "gocardless"
        assert inv.status == "paid"


def test_gocardless_test_connection(app_client, monkeypatch):
    headers, _org_id, _user_id = _seed_user(app_client, email="phase7_gc_test@example.com", superuser=True)
    app_client.put(
        "/admin/integrations/gocardless",
        json={
            "is_enabled": True,
            "config": {
                "access_token": "sandbox-token",
                "environment": "sandbox",
            },
        },
        headers=headers,
    )

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"creditors": [{"id": "CR123", "name": "Sandbox Creditor"}]}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            assert url.endswith("/creditors")
            return _FakeResponse()

    monkeypatch.setattr("app.services.gocardless_service.httpx.Client", _FakeClient)
    res = app_client.post("/admin/integrations/gocardless/test", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["environment"] == "sandbox"
    assert body["creditor_name"] == "Sandbox Creditor"


def test_cash_subscription_requires_admin_approval(app_client):
    headers, org_id, _user_id = _seed_user(app_client, email="phase7_cash@example.com", superuser=True)
    admin_headers = headers
    plans = app_client.get("/billing/plans").json()
    target = plans[1] if len(plans) > 1 else plans[0]

    change = app_client.post("/billing/subscription/change-plan", json={"plan_id": target["id"]}, headers=headers)
    assert change.status_code == 200
    body = change.json()
    assert body["awaiting_admin_approval"] is True
    assert body["subscription"]["status"] == "pending_payment"
    assert body["subscription"]["payment_provider"] == "manual_cash"

    sub = app_client.get("/billing/subscription", headers=headers).json()
    assert sub["pending_plan"]["id"] == target["id"]
    assert sub["plan"]["id"] != target["id"] or sub["subscription"]["status"] == "pending_payment"

    pending = app_client.get("/admin/billing/subscriptions/pending-cash", headers=admin_headers).json()
    assert any(row["org_id"] == org_id for row in pending)

    approve = app_client.post(f"/admin/billing/subscriptions/{org_id}/approve-cash", headers=admin_headers)
    assert approve.status_code == 200
    assert approve.json()["subscription"]["status"] == "active"

    sub_after = app_client.get("/billing/subscription", headers=headers).json()
    assert sub_after["plan"]["id"] == target["id"]
    assert sub_after.get("pending_plan") is None


def test_support_ticket_admin_reply_creates_user_notification(app_client):
    user_headers, _org_id, _user_id = _seed_user(app_client, email="phase7_support_user@example.com")
    admin_headers, _admin_org_id, _admin_id = _seed_user(app_client, email="phase7_support_admin@example.com", superuser=True)

    created = app_client.post(
        "/support/tickets",
        json={"category": "technical", "subject": "Phase 7 smoke ticket", "message": "Please help"},
        headers=user_headers,
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    detail = app_client.get(f"/admin/support/tickets/{ticket_id}", headers=admin_headers)
    assert detail.status_code == 200
    reply = app_client.post(f"/admin/support/tickets/{ticket_id}/reply", json={"message": "We are checking this."}, headers=admin_headers)
    assert reply.status_code == 200

    unread = app_client.get("/notifications/unread-count", headers=user_headers)
    assert unread.status_code == 200
    assert unread.json()["count"] >= 1

    open_ticket = app_client.get(f"/support/tickets/{ticket_id}", headers=user_headers)
    assert open_ticket.status_code == 200
    unread_after = app_client.get("/notifications/unread-count", headers=user_headers)
    assert unread_after.status_code == 200
    assert unread_after.json()["count"] == 0


def test_faq_admin_publish_and_dashboard_search_smoke(app_client):
    user_headers, _org_id, _user_id = _seed_user(app_client, email="phase7_faq_user@example.com")
    admin_headers, _admin_org_id, _admin_id = _seed_user(app_client, email="phase7_faq_admin@example.com", superuser=True)

    cat = app_client.post("/admin/faq/categories", json={"name": "Billing Help", "sort_order": 1}, headers=admin_headers)
    assert cat.status_code == 200
    item = app_client.post(
        "/admin/faq/items",
        json={
            "category_id": cat.json()["id"],
            "question": "How does sandbox billing work?",
            "answer": "Use GoCardless sandbox before going live.",
            "is_published": True,
            "is_featured": True,
            "sort_order": 1,
        },
        headers=admin_headers,
    )
    assert item.status_code == 200

    faq = app_client.get("/faq?search=sandbox", headers=user_headers)
    assert faq.status_code == 200
    groups = faq.json()
    assert groups
    assert groups[0]["items"][0]["question"] == "How does sandbox billing work?"


def test_admin_operations_retry_recovery_job_and_webhook_smoke(app_client):
    admin_headers, org_id, _admin_id = _seed_user(app_client, email="phase7_ops_admin@example.com", superuser=True)
    with get_sessionmaker()() as db:
        appt = Appointment(
            org_id=org_id,
            scheduled_start=datetime.now(timezone.utc),
            status="scheduled",
            recovery_state="failed",
            recovery_last_error="previous failure",
        )
        db.add(appt)
        db.flush()
        job = RecoveryJob(
            org_id=org_id,
            appointment_id=appt.id,
            idempotency_key=f"phase7:{appt.id}",
            state="failed",
            attempts=1,
            last_error="previous failure",
        )
        db.add(job)
        event = WebhookEvent(provider="vapi", dedupe_key="phase7-vapi", status="failed", attempts=1, raw_body="{}")
        db.add(event)
        db.commit()
        job_id = job.id
        event_id = event.id

    jobs = app_client.get("/admin/operations/recovery-jobs?limit=10", headers=admin_headers)
    assert jobs.status_code == 200
    assert any(row["id"] == job_id for row in jobs.json())

    retry_job = app_client.post(f"/admin/operations/recovery-jobs/{job_id}/retry", headers=admin_headers)
    assert retry_job.status_code == 200
    assert retry_job.json()["ok"] is True

    retry_event = app_client.post(f"/admin/operations/webhooks/{event_id}/retry", headers=admin_headers)
    assert retry_event.status_code == 200
    assert retry_event.json()["ok"] is True

    webhooks = app_client.get("/admin/operations/webhooks?limit=10", headers=admin_headers)
    assert webhooks.status_code == 200
    assert any(row["id"] == event_id and row["status"] == "processed" for row in webhooks.json())
