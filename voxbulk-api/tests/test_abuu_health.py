from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _mk_superadmin(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu Org")
        db.add(org)
        db.flush()
        admin = User(
            email="abuu_super@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "abuu_super@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, org_id


def _mk_accountant(app_client, org_id: str):
    with get_sessionmaker()() as db:
        user = User(
            email=f"abuu_acct_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        db.add(
            AdminUser(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                role="accountant",
                is_active=True,
                is_superuser=False,
            )
        )
        db.add(OrganisationMembership(org_id=org_id, user_id=user.id))
        db.commit()
        email = user.email

    tok = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_abuu_health_requires_auth(app_client):
    resp = app_client.get("/admin/abuu/health")
    assert resp.status_code == 401


def test_abuu_health_forbidden_for_non_superadmin(app_client):
    headers, org_id = _mk_superadmin(app_client)
    acct_headers = _mk_accountant(app_client, org_id)
    resp = app_client.get("/admin/abuu/health", headers=acct_headers)
    assert resp.status_code == 403


def test_abuu_health_ok_for_superadmin(app_client):
    from app.core.abuu_database import run_abuu_migrations

    run_abuu_migrations()
    headers, _org_id = _mk_superadmin(app_client)
    resp = app_client.get("/admin/abuu/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["enabled"] is True
    assert body["migration_head"] == "0009_abuu_agent_kb_settings"
    assert body["tables_present"] is True
