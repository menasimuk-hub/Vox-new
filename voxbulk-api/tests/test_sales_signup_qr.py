"""Salesman signup QR — /sales/me signup_url and promo_code PATCH."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.sales_rep import SalesRep
from app.models.user import User


def _headers(app_client, *, email: str, password: str, org_id: str) -> dict[str, str]:
    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": password, "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_salesman(*, promo_code: str, email: str | None = None) -> tuple[str, str, str]:
    suffix = uuid.uuid4().hex[:8]
    email = email or f"sales-{suffix}@test.com"
    with get_sessionmaker()() as db:
        org = Organisation(name=f"Sales Org {suffix}")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        db.add(
            SalesRep(
                user_id=user.id,
                name="Sam Seller",
                kind="salesman",
                promo_code=promo_code,
                commission_pct=10,
                commission_type="month2",
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()
        return org.id, email, promo_code


def test_sales_me_includes_signup_url(app_client):
    code = f"QR{uuid.uuid4().hex[:6].upper()}"
    org_id, email, _ = _seed_salesman(promo_code=code)
    headers = _headers(app_client, email=email, password="pass123", org_id=org_id)

    me = app_client.get("/sales/me", headers=headers)
    assert me.status_code == 200, me.text
    rep = me.json()["rep"]
    assert rep["promo_code"] == code
    url = str(rep.get("signup_url") or "")
    assert "/signin?promo=" in url
    assert code in url


def test_sales_me_patch_promo_updates_signup_url_and_rejects_duplicate(app_client):
    code_a = f"QA{uuid.uuid4().hex[:6].upper()}"
    code_b = f"QB{uuid.uuid4().hex[:6].upper()}"
    org_a, email_a, _ = _seed_salesman(promo_code=code_a)
    _seed_salesman(promo_code=code_b)
    headers = _headers(app_client, email=email_a, password="pass123", org_id=org_a)

    taken = app_client.patch("/sales/me", headers=headers, json={"promo_code": code_b})
    assert taken.status_code == 400, taken.text

    new_code = f"QN{uuid.uuid4().hex[:6].upper()}"
    updated = app_client.patch("/sales/me", headers=headers, json={"promo_code": new_code})
    assert updated.status_code == 200, updated.text
    rep = updated.json()["rep"]
    assert rep["promo_code"] == new_code
    assert new_code in str(rep.get("signup_url") or "")
    assert "/signin?promo=" in str(rep.get("signup_url") or "")
