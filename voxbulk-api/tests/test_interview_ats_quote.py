"""Interview ATS quote endpoint."""
from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService


def _seed_user(app_client, *, email: str = "ats_quote@example.com"):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="ATS Clinic")
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


def _long_cv() -> str:
    return "Jane Doe\nBackend engineer with Python, FastAPI, and SQL experience. " * 4


def test_interview_ats_quote_returns_pricing(app_client):
    headers, _org_id = _seed_user(app_client)

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "interview",
            "title": "Backend developer",
            "config": {
                "role": "Backend developer",
                "criteria": "Python and API experience",
                "approved_script": "Tell me about your Python experience.",
            },
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]

    with get_sessionmaker()() as db:
        order = ServiceOrderService.get_order(db, order_id)
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Jane Doe",
                phone="+447700900123",
                email="jane@example.com",
                cv_text=_long_cv(),
            )
        )
        db.commit()

    quoted = app_client.get(f"/service-orders/{order_id}/interview/ats/quote", headers=headers)
    assert quoted.status_code == 200, quoted.text
    body = quoted.json()
    assert body["candidate_count"] == 1
    assert body["total_pence"] > 0
    assert body["unit_price_pence"] > 0
    assert body["total_gbp"].startswith("£")


def test_interview_ats_quote_skips_already_scored(app_client):
    headers, _org_id = _seed_user(app_client, email="ats_quote2@example.com")

    created = app_client.post(
        "/service-orders",
        json={
            "service_code": "interview",
            "title": "Backend developer",
            "config": {"role": "Backend developer", "criteria": "Python"},
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]

    with get_sessionmaker()() as db:
        order = ServiceOrderService.get_order(db, order_id)
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Jane Doe",
                cv_text=_long_cv(),
                ats_status="complete",
                ats_score=88,
            )
        )
        db.commit()

    quoted = app_client.get(f"/service-orders/{order_id}/interview/ats/quote", headers=headers)
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["candidate_count"] == 0
