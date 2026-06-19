"""Per-provider deep health checks with mocked HTTP."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="Test Org")
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


def _set_scheduling(session, org_id, payload: dict[str, Any]):
    from app.services.scheduling_connection_service import save_scheduling_config

    save_scheduling_config(session, org_id, payload)


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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, *args, **kwargs):
        for key, resp in self._responses:
            if key in url:
                return resp
        return _Resp(404, payload={}, text="no fake response")

    def post(self, url: str, *args, **kwargs):
        return self.get(url, *args, **kwargs)


def _patch_httpx(monkeypatch, responses: dict[str, _Resp]):
    def factory(*args, **kwargs):
        return _FakeClient(responses)

    monkeypatch.setattr(httpx, "Client", factory)


def test_calendly_ok(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {
            "provider": "calendly",
            "access_token": "tok",
            "owner_uri": "https://api.calendly.com/users/abc",
            "event_type_uri": "https://api.calendly.com/event_types/xyz",
        },
    )
    _patch_httpx(
        monkeypatch,
        {
            "/users/me": _Resp(
                200,
                payload={"resource": {"uri": "https://api.calendly.com/users/abc", "name": "Jane"}},
            ),
            "/event_types": _Resp(
                200,
                payload={"collection": [{"uri": "https://api.calendly.com/event_types/xyz"}]},
            ),
        },
    )

    result = deep_health_check(session, org.id, "calendly")
    assert result["ok"] is True
    names = [c["name"] for c in result["checks"]]
    assert "token" in names and "event_type" in names


def test_calendly_invalid_token(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {"provider": "calendly", "access_token": "tok", "event_type_uri": "https://api.calendly.com/event_types/xyz"},
    )
    _patch_httpx(
        monkeypatch,
        {
            "/users/me": _Resp(401, payload={"error": "invalid"}, text="unauthorized"),
        },
    )

    result = deep_health_check(session, org.id, "calendly")
    assert result["ok"] is False
    assert any(c["status"] == "fail" and c["name"] == "token" for c in result["checks"])


def test_google_calendar_missing_scopes(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {
            "provider": "google_calendar",
            "access_token": "tok",
            "schedule_url": "https://calendar.app.google/abc",
        },
    )
    _patch_httpx(
        monkeypatch,
        {
            "userinfo": _Resp(200, payload={"email": "owner@example.com"}),
            "calendarList": _Resp(403, payload={"error": "insufficient_scopes"}, text="403"),
        },
    )

    result = deep_health_check(session, org.id, "google_calendar")
    assert result["ok"] is False
    assert any(c["name"] == "scopes" for c in result["checks"])


def test_microsoft_calendar_ok(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {
            "provider": "microsoft_calendar",
            "access_token": "tok",
            "schedule_url": "https://outlook.office365.com/owa/calendar/foo/bookings/",
        },
    )
    _patch_httpx(
        monkeypatch,
        {
            "graph.microsoft.com/v1.0/me/calendars": _Resp(
                200, payload={"value": [{"id": "c1", "name": "Calendar"}]}
            ),
            "graph.microsoft.com/v1.0/me": _Resp(
                200, payload={"displayName": "Jane", "userPrincipalName": "jane@example.com"}
            ),
        },
    )

    result = deep_health_check(session, org.id, "microsoft_calendar")
    assert result["ok"] is True


def test_cal_com_selected_event_type_missing(session, monkeypatch):
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {
            "provider": "cal_com",
            "access_token": "tok",
            "event_type_id": "999",
            "username": "user",
        },
    )
    _patch_httpx(
        monkeypatch,
        {
            "/v2/me": _Resp(200, payload={"data": {"email": "u@example.com", "username": "user"}}),
            "/v2/event-types": _Resp(
                200, payload={"data": [{"id": "111", "slug": "intro"}]}
            ),
        },
    )

    result = deep_health_check(session, org.id, "cal_com")
    assert result["ok"] is False
    assert any(c["name"] == "selected_event_type" and c["status"] == "fail" for c in result["checks"])


def test_hubspot_meetings_requires_oauth(session, monkeypatch):
    from app.services.hubspot_connection_service import save_hubspot_config
    from app.services.integration_test_service import deep_health_check

    org = _seed_org(session)
    _set_scheduling(
        session,
        org.id,
        {"provider": "hubspot_meetings", "meeting_link_url": "https://meetings.hubspot.com/x"},
    )
    save_hubspot_config(
        session,
        org.id,
        {
            "auth_mode": "private_app",
            "access_token": "pat-dummy",
            "account_name": "Acme",
        },
    )

    result = deep_health_check(session, org.id, "hubspot_meetings")
    assert result["ok"] is False
    # Private-app mode cannot list meeting links, so auth_mode check fires.
    assert any(c["name"] == "auth_mode" for c in result["checks"])


def test_unknown_provider_raises(session):
    from app.services.integration_test_service import IntegrationTestError, deep_health_check

    org = _seed_org(session)
    with pytest.raises(IntegrationTestError):
        deep_health_check(session, org.id, "no_such_provider")
