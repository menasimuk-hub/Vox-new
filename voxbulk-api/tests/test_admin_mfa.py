"""Platform-admin TOTP and production Redis rate-limit behaviour."""

from __future__ import annotations

import pyotp

from app.core.config import get_settings
from app.core.security import hash_password
from app.services.auth_rate_limit import _memory_buckets, check_auth_rate_limit
from app.services.sliding_window_rate_limit import check_sliding_window


def _seed_superuser(db, *, email: str, password: str = "pass123"):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="MFA Org")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password(password), is_active=True, is_superuser=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def test_superuser_mfa_required_then_accepts_code(app_client):
    from sqlalchemy import select
    from app.core.database import get_sessionmaker
    from app.models.user import User
    from app.services import admin_mfa_service

    with get_sessionmaker()() as db:
        user, org = _seed_superuser(db, email="mfa-admin@example.com")
        setup = admin_mfa_service.start_setup(user)
        admin_mfa_service.enable(user, pyotp.TOTP(setup["secret"]).now())
        db.add(user)
        db.commit()
        email = user.email
        org_id = org.id
        secret = setup["secret"]

    blocked = app_client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "mfa_required"

    ok = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id, "totp": pyotp.TOTP(secret).now()},
    )
    assert ok.status_code == 200
    assert ok.json().get("access_token")

    with get_sessionmaker()() as db:
        row = db.execute(select(User).where(User.email == email)).scalar_one()
        assert row.mfa_enabled is True


def test_tenant_cannot_setup_mfa(app_client):
    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    with get_sessionmaker()() as db:
        org = Organisation(name="Tenant MFA")
        db.add(org)
        db.flush()
        user = User(
            email="tenant-mfa@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        db.commit()
        token_res = app_client.post(
            "/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id}
        )
    assert token_res.status_code == 200
    headers = {"Authorization": f"Bearer {token_res.json()['access_token']}"}
    setup = app_client.post("/auth/me/mfa/setup", headers=headers)
    assert setup.status_code == 403


def test_production_redis_down_fails_open_without_memory(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/15")
    get_settings.cache_clear()
    _memory_buckets.clear()
    try:
        d = check_sliding_window(key="prod-fail-open", limit=1, window_sec=60, log_name="test_rl")
        assert d.allowed is True
        assert len(_memory_buckets.get("prod-fail-open", ())) == 0
        d2 = check_auth_rate_limit(scope="unit-prod", identity="ip-x", limit=1)
        assert d2.allowed is True
    finally:
        monkeypatch.setenv("ENV", "test")
        get_settings.cache_clear()
        _memory_buckets.clear()
