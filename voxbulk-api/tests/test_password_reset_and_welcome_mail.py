from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import secrets
from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.core.security import hash_password, verify_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.email_template_service import EmailTemplateService
from app.services.password_reset_service import reset_token_hmac
from app.services.transactional_email_service import TransactionalEmailService


def _seed_templates():
    with get_sessionmaker()() as db:
        for key in ("forgot_password", "new_user"):
            if EmailTemplateService.get(db, key=key) is None:
                EmailTemplateService.upsert(db, key=key, subject="S", body="Hello {{user_email}}", is_enabled=True)


def _make_user(email: str) -> tuple[str, str]:
    """Returns (org_id, user_email)."""
    with get_sessionmaker()() as db:
        org = Organisation(name=f"Pwd {email}")
        db.add(org)
        db.flush()
        u = User(
            email=email,
            password_hash=hash_password("oldpass12"),
            is_active=True,
            is_superuser=False,
        )
        db.add(u)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=u.id))
        db.commit()
        return str(org.id), email


def test_forgot_password_same_message_unknown_or_known(app_client):
    _seed_templates()
    _make_user("fp_user@example.com")

    with patch.object(TransactionalEmailService, "send_templated_optional", return_value=(True, None)):
        r1 = app_client.post("/auth/forgot-password", json={"email": "missing@example.com"})
        r2 = app_client.post("/auth/forgot-password", json={"email": "fp_user@example.com"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json().get("message") == r2.json().get("message")

    with get_sessionmaker()() as db:
        n = db.execute(select(func.count()).select_from(PasswordResetToken)).scalar_one()
    assert int(n) >= 1


def test_reset_password_bad_token(app_client):
    r = app_client.post("/auth/reset-password", json={"token": "x" * 40, "password": "newpw12345"})
    assert r.status_code == 400


def test_reset_password_success_and_single_use(app_client):
    _seed_templates()
    _make_user("reset_ok@example.com")

    raw = secrets.token_urlsafe(32)
    h = reset_token_hmac(raw)
    with get_sessionmaker()() as db:
        uid = db.execute(select(User.id).where(User.email == "reset_ok@example.com")).scalar_one()
        db.add(
            PasswordResetToken(
                user_id=uid,
                token_hmac=h,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
        )
        db.commit()

    r_ok = app_client.post("/auth/reset-password", json={"token": raw, "password": "brandnew1"})
    assert r_ok.status_code == 200

    with get_sessionmaker()() as db:
        u = db.execute(select(User).where(User.email == "reset_ok@example.com")).scalar_one()
        assert verify_password("brandnew1", u.password_hash)

    r_twice = app_client.post("/auth/reset-password", json={"token": raw, "password": "otherpass1"})
    assert r_twice.status_code == 400


def test_register_calls_new_user_email_hook(app_client):
    _seed_templates()

    with patch.object(TransactionalEmailService, "send_templated_optional", return_value=(True, None)) as m:
        r = app_client.post(
            "/auth/register",
            json={
                "email": "welcome_new@example.com",
                "password": "pw12345678",
                "organisation_name": "Welcome Co",
            },
        )
    assert r.status_code == 200
    kw = m.call_args.kwargs
    assert kw.get("template_key") == "new_user"
    assert kw.get("to_email") == "welcome_new@example.com"


def test_register_rejects_org_id_join(app_client):
    oid, _ = _make_user("anchor@example.com")
    r = app_client.post(
        "/auth/register",
        json={
            "email": "joiner@example.com",
            "password": "pw12345678",
            "organisation_name": "Ignored",
            "org_id": str(oid),
        },
    )
    assert r.status_code == 400
    assert "invite" in str(r.json().get("detail") or "").lower()
