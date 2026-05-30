"""Interview order quote and launch for monthly package subscribers."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.service_order import ServiceOrderRecipient
from app.models.subscription import Subscription
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService


def _plan(db, *, code: str, name: str, price: int = 12900) -> Plan:
    existing = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Plan(
        id=str(uuid.uuid4()),
        code=code,
        name=name,
        price_gbp_pence=price,
        interval="monthly",
        service_kind="voxbulk",
    )
    db.add(row)
    db.flush()
    return row


def _seed_pro_user(app_client, *, email: str = "pro_quote@example.com"):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Pro Clinic")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        pro = _plan(db, code="pro", name="Pro")
        db.add(
            Subscription(
                org_id=org.id,
                plan_id=pro.id,
                status="active",
                payment_provider="gocardless",
            )
        )
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def _add_recipient(order_id: str) -> None:
    with get_sessionmaker()() as db:
        order = ServiceOrderService.get_order(db, order_id)
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Jane Doe",
                phone="+447700900123",
                email="jane@example.com",
            )
        )
        order.recipient_count = 1
        db.add(order)
        db.commit()


def test_interview_quote_included_for_pro_package(app_client):
    headers, _org_id = _seed_pro_user(app_client)

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "interview",
            "title": "Backend developer",
            "config": {
                "role": "Backend developer",
                "criteria": "Python",
                "approved_script": "Tell me about Python.",
                "script_approved": True,
            },
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]
    _add_recipient(order_id)

    quoted = app_client.post(f"/service-orders/{order_id}/quote", headers=headers)
    assert quoted.status_code == 200, quoted.text
    body = quoted.json()
    assert body.get("included_in_package") is True
    assert body["quote_total_pence"] == 0
    assert "Included in Pro" in str(body.get("quote_total_display") or "")


def test_interview_launch_without_checkout_for_pro_package(app_client, monkeypatch):
    headers, _org_id = _seed_pro_user(app_client, email="pro_launch@example.com")

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "interview",
            "title": "Backend developer",
            "config": {
                "role": "Backend developer",
                "delivery": "ai_call",
                "criteria": "Python",
                "approved_script": "Tell me about Python.",
                "script_approved": True,
            },
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]
    _add_recipient(order_id)

    patched = app_client.patch(
        f"/service-orders/{order_id}",
        json={
            "scheduled_start_at": "2026-06-01T09:00:00",
            "scheduled_end_at": "2026-06-01T17:00:00",
        },
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    monkeypatch.setattr(
        "app.services.interview_launch_service.InterviewBookingService.send_invites",
        lambda *a, **k: {"ok": True, "whatsapp_sent": 1, "email_sent": 0, "errors": []},
    )

    launched = app_client.post(f"/service-orders/{order_id}/interview/launch", headers=headers)
    assert launched.status_code == 200, launched.text
    assert launched.json().get("ok") is True

    with get_sessionmaker()() as db:
        order = ServiceOrderService.get_order(db, order_id)
        assert order.payment_status == "approved"
        assert order.payment_method == "subscription"
