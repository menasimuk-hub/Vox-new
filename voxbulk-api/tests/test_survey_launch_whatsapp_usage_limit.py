"""Launch eligibility when WA allowance is exhausted on a package plan."""

from __future__ import annotations

import io
from datetime import datetime, timedelta

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityService


def _seed_user(app_client, *, email: str, whatsapp_included: int = 86, whatsapp_used: int = 124):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Allowance Exhausted Clinic")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        now = datetime.utcnow()
        db.add(
            OrgUsagePeriod(
                org_id=org.id,
                period_start=now,
                period_end=now + timedelta(days=30),
                status="active",
                plan_code="pro",
                whatsapp_included=whatsapp_included,
                whatsapp_used=whatsapp_used,
            )
        )
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_wa_order_with_contact(app_client, headers):
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
    upload = app_client.post(
        f"/service-orders/{order_id}/recipients/upload",
        headers=headers,
        files={"file": ("contacts.csv", io.BytesIO(b"name,phone\nAlex,+447700900121"), "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    return order_id


def test_allowance_exhausted_package_can_still_launch(app_client):
    headers = _seed_user(app_client, email="wa_usage_limit@example.com")
    order_id = _create_wa_order_with_contact(app_client, headers)

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_launch"] is True
    assert body["launch_action"] == "launch"
    assert body["mode"] == "subscription_overage"
    assert body["payment_required"] is False
    assert body["billing"]["whatsapp_included"] == 86
    assert body["billing"]["whatsapp_used"] == 124
    assert body["billing"]["whatsapp_remaining"] == 0
    assert body.get("extra_recipients") == 1
    assert body.get("amount_due_pence", 0) == 49
    assert "Plan includes:" in (body.get("summary") or "")
    assert "Extra recipients:" in (body.get("summary") or "")


def test_compute_cached_dedupes_within_ttl(app_client):
    headers = _seed_user(app_client, email="wa_cache_dedupe@example.com")
    order_id = _create_wa_order_with_contact(app_client, headers)

    first = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    second = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["mode"] == second.json()["mode"]

    refreshed = app_client.get(
        f"/service-orders/{order_id}/launch-eligibility?refresh=1",
        headers=headers,
    )
    assert refreshed.status_code == 200


def test_compute_allowance_exhausted_allows_launch_with_invoice(app_client):
    headers = _seed_user(app_client, email="wa_usage_limit_compute@example.com")
    order_id = _create_wa_order_with_contact(app_client, headers)
    with get_sessionmaker()() as db:
        from app.models.service_order import ServiceOrder

        order = db.get(ServiceOrder, order_id)
        org = db.get(Organisation, order.org_id)
        result = SurveyLaunchEligibilityService.compute(db, order, org)
    assert result["can_launch"] is True
    assert result["launch_action"] == "launch"
    assert result["mode"] == "subscription_overage"
    assert result["extra_recipients"] == 1
