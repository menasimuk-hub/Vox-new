"""Cal.com OAuth and platform config tests."""

from __future__ import annotations

import httpx
import pytest


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, _Resp]):
        self._responses = responses
        self.last_post_url = ""
        self.last_post_json = None
        self.last_post_data = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, *args, **kwargs):
        for key, resp in self._responses.items():
            if key in url:
                return resp
        return _Resp(404, text="no fake response")

    def post(self, url: str, *args, **kwargs):
        self.last_post_url = url
        self.last_post_json = kwargs.get("json")
        self.last_post_data = kwargs.get("data")
        for key, resp in self._responses.items():
            if key in url:
                return resp
        return _Resp(404, text="no fake response")


def _patch_httpx(monkeypatch, responses: dict[str, _Resp]):
    def factory(*args, **kwargs):
        return _FakeClient(responses)

    monkeypatch.setattr(httpx, "Client", factory)


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="Cal Org")
    db.add(org)
    db.flush()
    db.commit()
    return org


def _seed_admin(db):
    from app.services.provider_settings import ProviderSettingsService

    ProviderSettingsService.upsert_platform_config(
        db,
        provider="cal_com",
        is_enabled=True,
        visible_to_orgs=True,
        config={
            "client_id": "cal-client-123",
            "client_secret": "cal-secret-456",
            "redirect_uri": "https://api.test/service-orders/scheduling/oauth/cal-com/callback",
        },
    )


def test_cal_com_oauth_start_includes_scope(session):
    from app.services.cal_com_connection_service import (
        CAL_COM_OAUTH_SCOPES,
        cal_com_oauth_start,
    )

    org = _seed_org(session)
    _seed_admin(session)

    url = cal_com_oauth_start(org_id=org.id, db=session)
    assert url.startswith("https://app.cal.com/auth/oauth2/authorize?")
    assert "client_id=cal-client-123" in url
    assert "scope=" in url
    assert "EVENT_TYPE_READ" in url or CAL_COM_OAUTH_SCOPES.replace(" ", "+") in url


def test_cal_com_oauth_complete_uses_v2_token_endpoint(session, monkeypatch):
    from app.services.cal_com_connection_service import cal_com_oauth_complete
    from app.services.scheduling_connection_service import get_scheduling_config

    org = _seed_org(session)
    _seed_admin(session)
    state = f"{org.id}:nonce"

    fake = _FakeClient(
        {
            "/v2/auth/oauth2/token": _Resp(
                200,
                payload={
                    "access_token": "cal-access",
                    "refresh_token": "cal-refresh",
                    "expires_in": 1800,
                },
            ),
            "/v2/me": _Resp(200, payload={"data": {"email": "user@cal.com", "username": "user"}}),
            "/v2/event-types": _Resp(
                200,
                payload={"data": [{"id": "1", "slug": "30min", "link": "https://cal.com/user/30min"}]},
            ),
        }
    )
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake)

    cal_com_oauth_complete(session, code="auth-code", state=state)
    assert fake.last_post_url == "https://api.cal.com/v2/auth/oauth2/token"
    assert "/v2/oauth/" not in fake.last_post_url
    assert fake.last_post_json["client_id"] == "cal-client-123"
    assert fake.last_post_json["code"] == "auth-code"

    cfg = get_scheduling_config(session, org.id)
    assert cfg.get("provider") == "cal_com"
    assert cfg.get("access_token") == "cal-access"


def test_cal_com_platform_test_client_not_found(session, monkeypatch):
    from app.services.cal_com_connection_service import test_cal_com_platform_config

    _seed_admin(session)
    _patch_httpx(
        monkeypatch,
        {
            "/v2/auth/oauth2/token": _Resp(
                401,
                payload={"error": "invalid_client", "error_description": "client_not_found"},
            ),
        },
    )

    result = test_cal_com_platform_config(session)
    assert result["ok"] is False
    assert result["credential_source"] == "admin_db"
    assert any(c["name"] == "cal_com_api" and c["status"] == "fail" for c in result["checks"])


def test_cal_com_platform_test_invalid_grant_means_ok(session, monkeypatch):
    from app.services.cal_com_connection_service import test_cal_com_platform_config

    _seed_admin(session)
    _patch_httpx(
        monkeypatch,
        {
            "/v2/auth/oauth2/token": _Resp(
                400,
                payload={"error": "invalid_grant", "error_description": "code_invalid_or_expired"},
            ),
        },
    )

    result = test_cal_com_platform_config(session)
    assert result["ok"] is True
    assert result["client_id_masked"].startswith("cal-clie")
    assert any(c["name"] == "cal_com_api" and c["status"] == "ok" for c in result["checks"])


def test_cal_com_platform_test_invalid_secret(session, monkeypatch):
    from app.services.cal_com_connection_service import test_cal_com_platform_config

    _seed_admin(session)
    _patch_httpx(
        monkeypatch,
        {
            "/v2/auth/oauth2/token": _Resp(
                401,
                payload={"error": "invalid_client", "error_description": "invalid_client_credentials"},
            ),
        },
    )

    result = test_cal_com_platform_config(session)
    assert result["ok"] is False
    assert any("secret" in c["message"].lower() for c in result["checks"] if c["name"] == "cal_com_api")
