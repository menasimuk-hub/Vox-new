"""Organisation Control Center — country filter, billing actions, audit trail."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_billing_profile_service import sync_org_country_code
from app.services.platform_catalog_service import PlatformCatalogService


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Org")
        db.add(org)
        db.flush()
        user = User(
            email=f"occ-admin-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        email = user.email

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_customer_org(*, country: str = "United Kingdom", billing_currency: str | None = "GBP") -> str:
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(
            name=f"OCC Customer {uuid.uuid4().hex[:6]}",
            country=country,
            billing_currency=billing_currency,
            contact_email=f"occ-{uuid.uuid4().hex[:8]}@example.com",
        )
        db.add(org)
        db.commit()
        sync_org_country_code(db, org, commit=True)
        return org.id


def test_control_center_list_filters_by_country(app_client):
    admin = _admin_headers(app_client)
    uk_id = _seed_customer_org(country="United Kingdom")
    ca_id = _seed_customer_org(country="Canada", billing_currency="CAD")

    all_rows = app_client.get("/admin/organisations/control-center", headers=admin)
    assert all_rows.status_code == 200, all_rows.text
    ids = {row["id"] for row in all_rows.json()["items"]}
    assert uk_id in ids
    assert ca_id in ids

    uk_only = app_client.get("/admin/organisations/control-center?country=gb", headers=admin)
    assert uk_only.status_code == 200, uk_only.text
    uk_ids = {row["id"] for row in uk_only.json()["items"]}
    assert uk_id in uk_ids
    assert ca_id not in uk_ids


def test_control_center_detail_includes_billing_profile(app_client):
    admin = _admin_headers(app_client)
    org_id = _seed_customer_org(country="United Kingdom", billing_currency="GBP")

    detail = app_client.get(f"/admin/organisations/{org_id}/control-center", headers=admin)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["organisation"]["country"] == "United Kingdom"
    assert body["billing_profile"]["billing_currency"] == "GBP"
    assert body["billing_profile"]["country_code"] == "GB"
    assert "wallet_history" in body
    assert "activity" in body


def test_control_center_wallet_credit_and_audit(app_client):
    admin = _admin_headers(app_client)
    org_id = _seed_customer_org()

    credited = app_client.post(
        f"/admin/organisations/{org_id}/control-center/wallet/credit",
        headers=admin,
        json={"amount_minor": 2500, "reason": "Support goodwill"},
    )
    assert credited.status_code == 200, credited.text
    assert credited.json()["wallet_balance_pence"] == 2500

    detail = app_client.get(f"/admin/organisations/{org_id}/control-center", headers=admin)
    assert detail.status_code == 200
    events = detail.json()["activity"]
    assert any(e.get("event_type") == "wallet.credit" for e in events)


def test_control_center_overage_toggle(app_client):
    admin = _admin_headers(app_client)
    org_id = _seed_customer_org()

    disabled = app_client.patch(
        f"/admin/organisations/{org_id}/control-center/overage",
        headers=admin,
        json={"allow_overage": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["allow_overage"] is False

    detail = app_client.get(f"/admin/organisations/{org_id}/control-center", headers=admin)
    assert detail.json()["billing_profile"]["allow_overage"] is False
    assert any(e.get("event_type") == "overage.toggle" for e in detail.json()["activity"])


@patch("app.services.org_control_center_actions_service.OrgControlCenterActionsService._send_invoice_email", return_value=True)
def test_control_center_create_invoice(mock_send, app_client):
    admin = _admin_headers(app_client)
    org_id = _seed_customer_org()

    created = app_client.post(
        f"/admin/organisations/{org_id}/control-center/invoices",
        headers=admin,
        json={
            "amount_minor": 9900,
            "invoice_type": "manual",
            "due_date": "2026-07-01",
            "note": "Manual support invoice",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["ok"] is True
    assert body["invoice"]["status"] in {"due", "open", "issued"}
    assert body["emailed"] is True
    mock_send.assert_called_once()

    detail = app_client.get(f"/admin/organisations/{org_id}/control-center", headers=admin)
    invoice_ids = {inv["id"] for inv in detail.json()["invoices"]}
    assert body["invoice"]["id"] in invoice_ids


@patch("app.services.org_control_center_actions_service.OrgControlCenterActionsService._send_invoice_email", return_value=True)
def test_admin_created_invoice_visible_to_customer(mock_send, app_client):
    admin = _admin_headers(app_client)
    org_id = _seed_customer_org()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        user = User(
            email=org.contact_email,
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org_id, user_id=user.id, role="owner"))
        db.commit()
        customer_email = user.email

    customer_token = app_client.post(
        "/auth/token",
        data={"username": customer_email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    customer_headers = {"Authorization": f"Bearer {customer_token}"}

    created = app_client.post(
        f"/admin/organisations/{org_id}/control-center/invoices",
        headers=admin,
        json={"amount_minor": 5000, "invoice_type": "manual", "note": "Customer payable test"},
    )
    assert created.status_code == 200, created.text
    invoice_id = created.json()["invoice"]["id"]

    listed = app_client.get("/billing/invoices", headers=customer_headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    match = next((r for r in rows if r["id"] == invoice_id), None)
    assert match is not None
    assert match.get("payable") is True

    outstanding = app_client.get("/billing/invoices/outstanding", headers=customer_headers)
    assert outstanding.status_code == 200
    assert any(r["id"] == invoice_id for r in outstanding.json())

    usage = app_client.get("/billing/usage-summary", headers=customer_headers)
    assert usage.status_code == 200
    open_count = usage.json().get("billing_monitor", {}).get("status", {}).get("open_invoices_count", 0)
    assert open_count >= 1
