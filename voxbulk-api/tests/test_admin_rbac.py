from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _mk_superadmin(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="RBAC Org")
        db.add(org)
        db.flush()
        admin = User(email="rbac_super@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "rbac_super@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, org_id


def _token_for(app_client, email: str, password: str, org_id: str) -> dict[str, str]:
    tok = app_client.post(
        "/auth/token",
        data={"username": email, "password": password, "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_category_and_org_create_smoke(app_client):
    headers, org_id = _mk_superadmin(app_client)
    cat = app_client.post(
        "/admin/categories",
        json={"name": "Dental", "slug": f"dental-{uuid.uuid4().hex[:8]}", "description": None},
        headers=headers,
    )
    assert cat.status_code == 200
    org = app_client.post("/admin/organisations", json={"name": f"Clinic {uuid.uuid4().hex[:6]}"}, headers=headers)
    assert org.status_code == 200


def test_marketing_blocked_from_org_writes(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_m@example.com",
            "password": "pass123",
            "role": "marketing",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    h_m = _token_for(app_client, "rbac_m@example.com", "pass123", org_id)
    me = app_client.get("/auth/me", headers=h_m).json()
    assert me.get("admin_access") is True
    assert me.get("admin_role") == "marketing"

    slug = f"mkt-block-{uuid.uuid4().hex[:8]}"
    r = app_client.post(
        "/admin/categories",
        json={"name": "X", "slug": slug, "description": None},
        headers=h_m,
    )
    assert r.status_code == 403


def test_accountant_can_write_org_structure(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_a@example.com",
            "password": "pass123",
            "role": "accountant",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    h_a = _token_for(app_client, "rbac_a@example.com", "pass123", org_id)
    slug = f"acc-ok-{uuid.uuid4().hex[:8]}"
    r = app_client.post(
        "/admin/categories",
        json={"name": "Acc", "slug": slug, "description": None},
        headers=h_a,
    )
    assert r.status_code == 200


def test_marketing_blocked_from_billing_sink(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_m2@example.com",
            "password": "pass123",
            "role": "marketing",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    h_m = _token_for(app_client, "rbac_m2@example.com", "pass123", org_id)
    r = app_client.post(
        "/admin/billing/payment-events",
        json={
            "provider": "internal",
            "external_event_id": f"evt-{uuid.uuid4().hex}",
            "org_id": org_id,
            "client_email": "c@example.com",
            "status": "failed",
        },
        headers=h_m,
    )
    assert r.status_code == 403


def test_accountant_can_post_billing_event(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_a2@example.com",
            "password": "pass123",
            "role": "accountant",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    h_a = _token_for(app_client, "rbac_a2@example.com", "pass123", org_id)
    r = app_client.post(
        "/admin/billing/payment-events",
        json={
            "provider": "internal",
            "external_event_id": f"evt-{uuid.uuid4().hex}",
            "org_id": org_id,
            "client_email": "c@example.com",
            "status": "failed",
        },
        headers=h_a,
    )
    assert r.status_code == 200


def test_email_routes_role_matrix(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_m3@example.com",
            "password": "pass123",
            "role": "marketing",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_a3@example.com",
            "password": "pass123",
            "role": "accountant",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    h_m = _token_for(app_client, "rbac_m3@example.com", "pass123", org_id)
    h_a = _token_for(app_client, "rbac_a3@example.com", "pass123", org_id)

    gr = app_client.get("/admin/email/templates", headers=h_m)
    assert gr.status_code == 200

    br = app_client.get("/admin/email/templates", headers=h_a)
    assert br.status_code == 403


def test_admin_user_create_sets_user_superuser_false_for_roles(app_client):
    headers_super, org_id = _mk_superadmin(app_client)
    app_client.post(
        "/admin/admin-users",
        json={
            "email": "rbac_acc@example.com",
            "password": "pass123",
            "role": "accountant",
            "is_active": True,
            "is_superuser": False,
        },
        headers=headers_super,
    )
    with get_sessionmaker()() as db:
        u = db.execute(select(User).where(User.email == "rbac_acc@example.com")).scalar_one_or_none()
        assert u is not None
        assert u.is_superuser is False
