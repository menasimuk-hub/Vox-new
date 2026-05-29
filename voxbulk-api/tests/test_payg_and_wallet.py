"""Pay-as-you-go plan and admin wallet credit."""
from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.voxbulk_pricing_service import VoxbulkPricingService


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Org")
        db.add(org)
        db.flush()
        user = User(email="admin_payg@test.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": "admin_payg@test.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _customer_headers(app_client, *, email: str = "payg_user@test.com"):
    with get_sessionmaker()() as db:
        VoxbulkPricingService.ensure_seeded(db)
        org = Organisation(name="Customer Org")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
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


def test_payg_plan_is_seeded(app_client):
    headers, _org_id = _customer_headers(app_client)
    pricing = app_client.get("/billing/pricing", headers=headers)
    assert pricing.status_code == 200, pricing.text
    codes = [p["code"] for p in pricing.json()["plans"]]
    assert "payg" in codes
    payg = next(p for p in pricing.json()["plans"] if p["code"] == "payg")
    assert payg["is_payg"] is True
    assert payg["price_gbp_pence"] == 0


def test_switch_to_pay_as_you_go(app_client):
    headers, _org_id = _customer_headers(app_client, email="payg_switch@test.com")
    switched = app_client.post("/billing/subscription/pay-as-you-go", headers=headers)
    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["plan"]["code"] == "payg"
    assert body["subscription"]["status"] == "active"


def test_admin_wallet_credit(app_client):
    admin = _admin_headers(app_client)
    _, org_id = _customer_headers(app_client, email="wallet_credit@test.com")

    credited = app_client.post(
        f"/admin/organisations/{org_id}/wallet/credit",
        headers=admin,
        json={"amount_pence": 5000, "note": "Test"},
    )
    assert credited.status_code == 200, credited.text
    assert credited.json()["wallet_balance_pence"] == 5000

    org = app_client.get(f"/admin/organisations/{org_id}", headers=admin)
    assert org.status_code == 200
    assert org.json()["wallet_balance_pence"] == 5000
