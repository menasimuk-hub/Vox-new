from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from sqlalchemy import select

from app.models.user import User


def _mk_superadmin(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="AdminUser Org")
        db.add(org)
        db.flush()
        admin = User(email="superadmin@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post("/auth/token", data={"username": "superadmin@example.com", "password": "pass123", "org_id": org_id}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_admin_users_crud_requires_superadmin(app_client):
    # no token -> forbidden
    r = app_client.get("/admin/admin-users")
    assert r.status_code in (401, 403)


def test_admin_users_create_list_delete(app_client):
    headers = _mk_superadmin(app_client)

    r0 = app_client.get("/admin/admin-users", headers=headers)
    assert r0.status_code == 200

    create = app_client.post(
        "/admin/admin-users",
        json={"email": "ops@example.com", "password": "pass123", "is_active": True, "is_superuser": False, "role": "marketing"},
        headers=headers,
    )
    assert create.status_code == 200

    with get_sessionmaker()() as db:
        u_chk = db.execute(select(User).where(User.email == "ops@example.com")).scalar_one_or_none()
        assert u_chk is not None
        assert u_chk.is_superuser is False

    listed = app_client.get("/admin/admin-users", headers=headers).json()
    assert any(x["email"] == "ops@example.com" for x in listed)
    uid = next(x["id"] for x in listed if x["email"] == "ops@example.com")

    # delete disables backing user and removes admin_users row
    rdel = app_client.delete(f"/admin/admin-users/{uid}", headers=headers)
    assert rdel.status_code == 200

