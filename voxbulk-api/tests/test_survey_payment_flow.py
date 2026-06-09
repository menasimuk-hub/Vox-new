"""End-to-end survey payment flow (create → upload → quote → wallet top-up → launch)."""
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


def _create_wa_order(app_client, headers, *, title: str = "Wallet survey"):
    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "survey",
            "title": title,
            "config": {
                "survey_channel": "whatsapp",
                "delivery": "whatsapp",
                "channels": ["whatsapp"],
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
    return order_id


def test_survey_quote_uses_voxbulk_pricing(app_client):
    headers, _org_id = _seed_user(app_client)

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "survey",
            "title": "AI call survey",
            "config": {"survey_channel": "ai_call", "script_approved": True},
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
    assert upload.json()["status"] == "quoted"

    quoted = app_client.post(f"/service-orders/{order_id}/quote", headers=headers)
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["quote_total_pence"] > 0


def test_payg_launch_blocked_until_wallet_topup(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_wallet@example.com")
    order_id = _create_wa_order(app_client, headers)

    # No wallet balance, no subscription → launch requires a top-up.
    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_launch"] is False
    assert body["mode"] == "wallet_insufficient"
    assert body["launch_action"] == "topup_required"
    amount_due = int(body["amount_due_pence"] or 0)
    assert amount_due > 0

    launch = app_client.post(f"/service-orders/{order_id}/survey/launch", headers=headers, json={"run_mode": "now"})
    assert launch.status_code in {400, 402}

    # Top up the wallet (dev test-cash path) and relaunch.
    topup = app_client.post("/billing/wallet/topup", json={"amount_minor": 5000}, headers=headers)
    assert topup.status_code == 200, topup.text
    assert int(topup.json()["wallet_balance_pence"]) == 5000

    refreshed = app_client.get(f"/service-orders/{order_id}/launch-eligibility?refresh=1", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["can_launch"] is True
    assert body["mode"] == "wallet"
    assert body["launch_action"] == "launch"
    assert int(body["wallet_charge_minor"]) == amount_due

    launch = app_client.post(f"/service-orders/{order_id}/survey/launch", headers=headers, json={"run_mode": "now"})
    assert launch.status_code == 200, launch.text
    assert launch.json()["ok"] is True

    # Wallet was debited and the launch is recorded in the ledger.
    wallet = app_client.get("/billing/wallet", headers=headers)
    assert wallet.status_code == 200
    assert int(wallet.json()["wallet_balance_pence"]) == 5000 - amount_due

    txs = app_client.get("/billing/wallet/transactions", headers=headers)
    assert txs.status_code == 200
    kinds = [t["kind"] for t in txs.json()["transactions"]]
    assert "topup" in kinds
    assert "launch_debit" in kinds


def test_wallet_topup_intent_requires_known_provider(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_topup_intent@example.com")
    res = app_client.post(
        "/billing/wallet/topup/intent",
        json={"provider": "paypal", "amount_minor": 5000},
        headers=headers,
    )
    assert res.status_code == 400
    assert "stripe or airwallex" in res.json()["detail"].lower()


def test_wallet_topup_options_lists_currency(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_topup_options@example.com")
    res = app_client.get("/billing/wallet/topup/options", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["currency"] in {"GBP", "USD", "CAD", "AUD"}
    assert isinstance(body["providers"], list)
