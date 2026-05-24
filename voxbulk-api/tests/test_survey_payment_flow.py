"""End-to-end survey order payment flow (create → upload → schedule → quote → pay → schedule)."""
from __future__ import annotations

import io

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_user(app_client, *, email: str = "survey_pay@example.com", superuser: bool = False):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Survey Clinic")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True, is_superuser=superuser)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _csv_bytes():
    return b"name,phone,email\nSarah Ahmed,+447700900123,sarah@example.com\n"


def test_survey_cash_payment_flow(app_client):
    headers, _org_id = _seed_user(app_client)

    packages = app_client.get("/service-orders/survey-packages", headers=headers)
    assert packages.status_code == 200, packages.text
    pkg_list = packages.json()["packages"]["ai_call"]
    assert pkg_list, "expected ai_call packages"
    package_id = pkg_list[0]["id"]

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "survey",
            "title": "Test survey",
            "config": {
                "survey_channel": "ai_call",
                "package_id": package_id,
                "script_approved": True,
            },
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]

    upload = app_client.post(
        f"/service-orders/{order_id}/recipients/upload",
        headers=headers,
        files={"file": ("contacts.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["recipient_count"] == 1
    assert upload.json()["status"] == "quoted"

    patched = app_client.patch(
        f"/service-orders/{order_id}",
        json={
            "run_mode": "scheduled",
            "scheduled_start_at": "2026-06-01T09:00:00",
            "scheduled_end_at": "2026-06-01T17:00:00",
        },
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    quoted = app_client.post(f"/service-orders/{order_id}/quote", headers=headers)
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["quote_total_pence"] > 0

    paid = app_client.post(
        f"/service-orders/{order_id}/pay-cash",
        json={"note": "test cash"},
        headers=headers,
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["payment_status"] == "pending_approval"

    schedule_before_approve = app_client.post(f"/service-orders/{order_id}/schedule", headers=headers)
    assert schedule_before_approve.status_code == 400


def test_survey_gocardless_start_requires_quote(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_gc@example.com")

    created = app_client.post(
        "/service-orders",
        json={"service_code": "survey", "title": "GC survey", "config": {"survey_channel": "ai_call"}},
        headers=headers,
    )
    order_id = created.json()["id"]

    start = app_client.post(f"/service-orders/{order_id}/gocardless/start", headers=headers)
    assert start.status_code == 400
    assert "quote" in start.json()["detail"].lower()


def test_survey_gocardless_start_after_quote(app_client, monkeypatch):
    headers, _org_id = _seed_user(app_client, email="survey_gc_ok@example.com", superuser=True)

    packages = app_client.get("/service-orders/survey-packages", headers=headers).json()
    package_id = packages["packages"]["ai_call"][0]["id"]

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "survey",
            "title": "GC quoted survey",
            "config": {"survey_channel": "ai_call", "package_id": package_id},
        },
        headers=headers,
    )
    order_id = created.json()["id"]

    upload = app_client.post(
        f"/service-orders/{order_id}/recipients/upload",
        headers=headers,
        files={"file": ("contacts.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert upload.status_code == 200

    admin_headers = headers
    app_client.put(
        "/admin/integrations/gocardless",
        json={
            "is_enabled": True,
            "config": {
                "access_token": "sandbox-token",
                "environment": "sandbox",
                "webhook_secret": "gc-test",
            },
        },
        headers=admin_headers,
    )

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
                return _FakeResponse(
                    {"redirect_flows": {"id": "RE_SURVEY", "redirect_url": "https://pay-sandbox.example/survey-flow"}}
                )
            raise AssertionError(f"unexpected GoCardless URL: {url}")

    monkeypatch.setattr("app.services.gocardless_service.httpx.Client", _FakeClient)

    start = app_client.post(f"/service-orders/{order_id}/gocardless/start", headers=headers)
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["authorization_url"] == "https://pay-sandbox.example/survey-flow"
    assert body["redirect_flow_id"] == "RE_SURVEY"
