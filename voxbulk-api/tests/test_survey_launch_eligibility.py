"""Survey launch eligibility and server-side enforcement."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityService


def _seed_user(app_client, *, email: str, survey_credits: int = 0, whatsapp_included: int = 0):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Launch Clinic", survey_credits_balance=survey_credits)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        if whatsapp_included > 0:
            now = datetime.utcnow()
            db.add(
                OrgUsagePeriod(
                    org_id=org.id,
                    period_start=now,
                    period_end=now + timedelta(days=30),
                    status="active",
                    plan_code="pro",
                    whatsapp_included=whatsapp_included,
                    whatsapp_used=0,
                )
            )
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _csv_bytes(n: int = 2):
    lines = ["name,phone,email"]
    for i in range(n):
        lines.append(f"Person {i},+44770090012{i},p{i}@example.com")
    return "\n".join(lines).encode()


def _create_wa_order(app_client, headers, *, contact_count: int = 2):
    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "survey",
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
    lines = ["name,phone,email"]
    for i in range(contact_count):
        lines.append(f"Person {i},+44770090012{i},p{i}@example.com")
    upload = app_client.post(
        f"/service-orders/{order_id}/recipients/upload",
        headers=headers,
        files={"file": ("contacts.csv", io.BytesIO("\n".join(lines).encode()), "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    return order_id


def test_launch_eligibility_promo_credits_cover_full(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_launch_credits@example.com", survey_credits=5)
    order_id = _create_wa_order(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "promo_credits"
    assert body["can_launch"] is True
    assert body["payment_required"] is False
    assert body["launch_action"] == "launch"


def test_launch_eligibility_whatsapp_allowance_covers_full(app_client):
    headers, _org_id = _seed_user(
        app_client,
        email="survey_launch_wa@example.com",
        whatsapp_included=100,
    )
    order_id = _create_wa_order(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "subscription_whatsapp"
    assert body["can_launch"] is True
    assert body["payment_required"] is False


def test_launch_eligibility_partial_allowance_invoices_extra(app_client):
    headers, _org_id = _seed_user(
        app_client,
        email="survey_launch_partial@example.com",
        whatsapp_included=1,
    )
    order_id = _create_wa_order(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "subscription_overage"
    assert body["payment_required"] is False
    assert body["launch_action"] == "launch"
    assert body["can_launch"] is True
    assert body["covered_by_allowance"] == 1
    assert body["shortfall_units"] == 1
    assert body["extra_recipients"] == 1
    assert int(body["amount_due_pence"] or 0) == 49


def test_launch_eligibility_no_allowance_payg_blocked_until_topup(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_launch_payg@example.com")
    order_id = _create_wa_order(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "wallet_insufficient"
    assert body["can_launch"] is False
    assert body["payment_required"] is True
    assert body["launch_action"] == "topup_required"
    assert int(body["amount_due_pence"] or 0) > 0
    assert int(body["wallet_shortfall_minor"] or 0) > 0


def test_launch_eligibility_payg_wallet_covers(app_client):
    headers, org_id = _seed_user(app_client, email="survey_launch_wallet@example.com")
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        org.wallet_balance_pence = 10_000
        db.add(org)
        db.commit()
    order_id = _create_wa_order(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "wallet"
    assert body["can_launch"] is True
    assert body["launch_action"] == "launch"
    assert int(body["wallet_charge_minor"]) == int(body["amount_due_pence"])


def test_launch_with_promo_credits(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_launch_run@example.com", survey_credits=5)
    order_id = _create_wa_order(app_client, headers)

    detail = app_client.get(f"/service-orders/{order_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert str(detail.json().get("campaign_id") or "").startswith("VB-CMP-")

    launch = app_client.post(f"/service-orders/{order_id}/survey/launch", headers=headers, json={"run_mode": "now"})
    assert launch.status_code == 200, launch.text
    body = launch.json()
    assert body["ok"] is True
    assert body["order_id"] == order_id
    assert str(body.get("campaign_id") or "").startswith("VB-CMP-")


def test_payg_one_contact_pricing_breakdown(app_client):
    """1 WhatsApp contact on PAYG = 1 × wa_extra rate (default 49p)."""
    headers, _org_id = _seed_user(app_client, email="survey_launch_pricing@example.com")
    order_id = _create_wa_order(app_client, headers, contact_count=1)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("recipient_count") == 1
    assert body.get("estimated_whatsapp_usage") == 1
    assert body.get("launch_action") == "topup_required"
    assert int(body.get("amount_due_pence") or 0) == 49
    assert body.get("pricing_source") == "voxbulk_plan_prices"


def test_allowance_covers_launch_zero_due(app_client):
    headers, _org_id = _seed_user(
        app_client,
        email="survey_launch_allowance@example.com",
        whatsapp_included=100,
    )
    order_id = _create_wa_order(app_client, headers, contact_count=2)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("can_launch") is True
    assert body.get("payment_required") is False
    assert body.get("launch_action") == "launch"
    assert body.get("mode") == "subscription_whatsapp"
    assert body.get("covered_by_allowance") == 2

    after = app_client.get(f"/service-orders/{order_id}", headers=headers)
    assert after.status_code == 200, after.text
    assert str(after.json().get("campaign_id") or "").startswith("VB-CMP-")


def test_start_order_rejects_unpaid(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_launch_block@example.com")
    order_id = _create_wa_order(app_client, headers)

    start = app_client.post(f"/service-orders/{order_id}/start", headers=headers)
    assert start.status_code == 400
