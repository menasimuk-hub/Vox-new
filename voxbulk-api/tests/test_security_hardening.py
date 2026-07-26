"""Security hardening smoke tests (org-join, webhook fail-closed, JWT version)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_register_rejects_org_id_join_smoke(app_client: TestClient):
    first = app_client.post(
        "/auth/register",
        json={
            "email": "sec_owner@example.com",
            "password": "pw12345678",
            "organisation_name": "Sec Org",
        },
    )
    assert first.status_code == 200
    org_id = first.json()["org_id"]

    second = app_client.post(
        "/auth/register",
        json={
            "email": "sec_joiner@example.com",
            "password": "pw12345678",
            "organisation_name": "Other",
            "org_id": org_id,
        },
    )
    assert second.status_code == 400


def test_password_reset_invalidates_old_jwt(app_client: TestClient):
    from datetime import datetime, timedelta

    import secrets
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User
    from app.services.password_reset_service import reset_token_hmac

    reg = app_client.post(
        "/auth/register",
        json={
            "email": "sec_reset@example.com",
            "password": "oldpass12",
            "organisation_name": "Reset Org",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert app_client.get("/auth/me", headers=headers).status_code == 200

    raw = secrets.token_urlsafe(32)
    with get_sessionmaker()() as db:
        user = db.execute(select(User).where(User.email == "sec_reset@example.com")).scalar_one()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hmac=reset_token_hmac(raw),
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
        )
        db.commit()

    ok = app_client.post("/auth/reset-password", json={"token": raw, "password": "newpass12"})
    assert ok.status_code == 200
    assert app_client.get("/auth/me", headers=headers).status_code == 401


def test_telnyx_voice_webhook_unsigned_allowed_in_test_env(app_client: TestClient):
    # ENV=test in conftest → signature verify skipped when no public key
    r = app_client.post("/telnyx/webhooks/voice", json={"data": {"event_type": "call.initiated"}})
    assert r.status_code == 200


def test_celery_task_status_requires_auth(app_client: TestClient):
    assert app_client.get("/calls/recovery/tasks/fake-id").status_code == 401
    assert app_client.get("/dashboard/dentally/sync/fake-id").status_code == 401


def test_me_role_self_promote_forbidden(app_client: TestClient):
    reg = app_client.post(
        "/auth/register",
        json={
            "email": "sec_role@example.com",
            "password": "pw12345678",
            "organisation_name": "Role Org",
        },
    )
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    r = app_client.post("/auth/me/role", headers=headers, json={"role": "owner"})
    assert r.status_code == 403


def test_logout_invalidates_jwt(app_client: TestClient):
    reg = app_client.post(
        "/auth/register",
        json={
            "email": "sec_logout@example.com",
            "password": "pw12345678",
            "organisation_name": "Logout Org",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert app_client.get("/auth/me", headers=headers).status_code == 200
    assert app_client.post("/auth/logout", headers=headers).status_code == 200
    assert app_client.get("/auth/me", headers=headers).status_code == 401


def test_media_auth_headers_reject_substring_host_trick():
    from app.services.survey_wa_voice_note_media_service import _download_auth_headers
    from app.utils.safe_outbound_url import classify_media_download_host, media_url_hostname

    evil = "https://evil.example/?lookaside.fbsbx.com"
    assert classify_media_download_host(media_url_hostname(evil)) is None
    class _DummyDb:
        pass

    headers = _download_auth_headers(db=_DummyDb(), media_url=evil)
    assert "Authorization" not in headers
