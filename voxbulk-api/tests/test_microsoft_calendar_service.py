"""Microsoft 365 Calendar booking provider."""

from __future__ import annotations

from typing import Any

import httpx
import pytest


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="MS Org")
    db.add(org)
    db.flush()
    db.commit()
    return org


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()


class _Resp:
    def __init__(self, status_code: int, payload: dict | list | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, _Resp]):
        # Longer match keys win so /me/calendars beats /me.
        self._responses = sorted(responses.items(), key=lambda kv: len(kv[0]), reverse=True)
        self.last_request = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, *args, **kwargs):
        self.last_request = ("GET", url, kwargs)
        for key, resp in self._responses:
            if key in url:
                return resp
        return _Resp(404, payload={}, text="no fake response")

    def post(self, url: str, *args, **kwargs):
        self.last_request = ("POST", url, kwargs)
        for key, resp in self._responses:
            if key in url:
                return resp
        return _Resp(404, payload={}, text="no fake response")


def _patch_httpx(monkeypatch, responses: dict[str, _Resp]):
    def factory(*args, **kwargs):
        return _FakeClient(responses)

    monkeypatch.setattr(httpx, "Client", factory)


def _seed_admin(db, *, is_enabled=True, visible=True):
    from app.services.provider_settings import ProviderSettingsService

    ProviderSettingsService.upsert_platform_config(
        db,
        provider="microsoft_calendar",
        is_enabled=is_enabled,
        visible_to_orgs=visible,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://api.test/scheduling/oauth/microsoft-calendar/callback",
            "tenant": "common",
        },
    )


def test_oauth_start_includes_multi_tenant_common(session):
    from app.services.microsoft_calendar_service import microsoft_calendar_oauth_start

    org = _seed_org(session)
    _seed_admin(session)

    url = microsoft_calendar_oauth_start(org_id=org.id, db=session)
    assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
    assert "client_id=ms-client" in url
    assert "Calendars.ReadWrite" in url
    assert "User.Read" in url
    assert "offline_access" in url


def test_oauth_complete_persists_token(session, monkeypatch):
    from app.services.integration_catalogue_service import list_integrations_for_org
    from app.services.microsoft_calendar_service import microsoft_calendar_oauth_complete
    from app.services.scheduling_connection_service import get_scheduling_config

    org = _seed_org(session)
    _seed_admin(session)

    _patch_httpx(
        monkeypatch,
        {
            "/oauth2/v2.0/token": _Resp(
                200,
                payload={
                    "access_token": "AT",
                    "refresh_token": "RT",
                    "expires_in": 3600,
                },
            ),
            "graph.microsoft.com/v1.0/me": _Resp(
                200,
                payload={"displayName": "Jane", "userPrincipalName": "jane@example.com"},
            ),
        },
    )

    microsoft_calendar_oauth_complete(session, code="auth-code", state=f"{org.id}:nonce")
    cfg = get_scheduling_config(session, org.id)
    assert cfg["provider"] == "microsoft_calendar"
    assert cfg["access_token"] == "AT"
    assert cfg["owner_name"] == "Jane"
    assert cfg["owner_email"] == "jane@example.com"

    catalogue = list_integrations_for_org(session, org.id)
    ms = next(row for row in catalogue["booking"] if row["key"] == "microsoft_calendar")
    assert ms["connected"] is True
    assert ms["extra"]["event_type_configured"] is False


def test_select_schedule_requires_https(session, monkeypatch):
    from app.services.microsoft_calendar_service import (
        microsoft_calendar_oauth_complete,
        select_microsoft_calendar_schedule,
    )

    org = _seed_org(session)
    _seed_admin(session)

    _patch_httpx(
        monkeypatch,
        {
            "/oauth2/v2.0/token": _Resp(200, payload={"access_token": "AT", "expires_in": 3600}),
            "graph.microsoft.com/v1.0/me": _Resp(200, payload={"displayName": "Jane"}),
        },
    )
    microsoft_calendar_oauth_complete(session, code="auth-code", state=f"{org.id}:nonce")

    with pytest.raises(ValueError):
        select_microsoft_calendar_schedule(session, org.id, schedule_url="not-a-url")

    saved = select_microsoft_calendar_schedule(
        session, org.id, schedule_url="https://outlook.office365.com/owa/calendar/foo/bookings/"
    )
    assert saved.get("microsoft_calendar_connected") is True


def test_create_scheduling_link_appends_candidate_params(session, monkeypatch):
    from app.services.microsoft_calendar_service import (
        create_microsoft_calendar_scheduling_link,
        microsoft_calendar_oauth_complete,
        select_microsoft_calendar_schedule,
    )

    org = _seed_org(session)
    _seed_admin(session)
    _patch_httpx(
        monkeypatch,
        {
            "/oauth2/v2.0/token": _Resp(200, payload={"access_token": "AT", "expires_in": 3600}),
            "graph.microsoft.com/v1.0/me": _Resp(200, payload={"displayName": "Jane"}),
        },
    )
    microsoft_calendar_oauth_complete(session, code="auth-code", state=f"{org.id}:nonce")
    select_microsoft_calendar_schedule(
        session, org.id, schedule_url="https://outlook.office365.com/owa/calendar/foo/bookings/"
    )

    link = create_microsoft_calendar_scheduling_link(
        session, org.id, candidate_name="Alex", candidate_email="alex@example.com"
    )
    assert link.startswith("https://outlook.office365.com/owa/calendar/foo/bookings/")
    assert "email=alex%40example.com" in link
    assert "name=Alex" in link


def test_health_check_records_last_check_summary(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check
    from app.services.microsoft_calendar_service import microsoft_calendar_oauth_complete

    org = _seed_org(session)
    _seed_admin(session)
    _patch_httpx(
        monkeypatch,
        {
            "/oauth2/v2.0/token": _Resp(200, payload={"access_token": "AT", "expires_in": 3600}),
            "graph.microsoft.com/v1.0/me/calendars": _Resp(
                200, payload={"value": [{"id": "c1", "name": "Calendar"}]}
            ),
            "graph.microsoft.com/v1.0/me": _Resp(200, payload={"displayName": "Jane"}),
        },
    )
    microsoft_calendar_oauth_complete(session, code="auth-code", state=f"{org.id}:nonce")

    # No schedule URL yet, so schedule_url check should fail but token + calendars pass.
    result = deep_health_check(session, org.id, "microsoft_calendar")
    assert result["ok"] is False
    names = {c["name"] for c in result["checks"]}
    assert {"token", "calendars", "schedule_url"} <= names
