"""Unhandled exception JSON must not leak internals in production."""

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from main import _unhandled_exception_response_content


def test_production_500_is_generic_only():
    body = _unhandled_exception_response_content(
        RuntimeError("secret sql: SELECT * FROM users [parameters: ('+447700900123',)]"),
        "/organisations/me",
        env="production",
    )
    assert body == {"detail": "Internal server error"}
    assert "error_type" not in body
    assert "path" not in body
    assert "sql" not in body["detail"].lower()


def test_prod_alias_500_is_generic_only():
    body = _unhandled_exception_response_content(
        ValueError("boom"),
        "/debug",
        env="prod",
    )
    assert body == {"detail": "Internal server error"}


def test_development_500_includes_debug_fields():
    body = _unhandled_exception_response_content(
        RuntimeError("boom"),
        "/debug",
        env="development",
    )
    assert body["detail"] == "boom"
    assert body["error_type"] == "RuntimeError"
    assert body["path"] == "/debug"


def test_test_env_500_includes_debug_fields():
    body = _unhandled_exception_response_content(
        RuntimeError("boom"),
        "/debug",
        env="test",
    )
    assert body["error_type"] == "RuntimeError"
    assert body["path"] == "/debug"


def test_production_client_data_error_keeps_safe_detail():
    body = _unhandled_exception_response_content(
        RuntimeError("Data too long for column 'phone' at row 1"),
        "/contacts",
        env="production",
    )
    assert "error_type" not in body
    assert "path" not in body
    assert body["detail"] != "Internal server error"
    assert "phone" in body["detail"].lower()


def test_production_integrity_error_is_client_safe():
    body = _unhandled_exception_response_content(
        IntegrityError("INSERT", {}, Exception("Duplicate entry 'x' for key 'email'")),
        "/users",
        env="production",
    )
    assert body["detail"] != "Internal server error"
    assert "error_type" not in body


def test_sentry_before_send_strips_jwt_and_phone():
    from app.core.sentry import before_send

    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer super-secret-jwt",
                "X-Health-Token": "health-secret",
                "Content-Type": "application/json",
            },
            "cookies": {"session": "abc"},
            "data": {"phone": "+447700900123", "name": "Ada"},
        },
        "extra": {"access_token": "tok", "path": "/health"},
    }
    out = before_send(event, None)
    assert out is not None
    headers = out["request"]["headers"]
    assert headers["Authorization"] == "[Filtered]"
    assert headers["X-Health-Token"] == "[Filtered]"
    assert headers["Content-Type"] == "application/json"
    assert out["request"]["cookies"] == "[Filtered]"
    assert out["request"]["data"]["phone"] == "[Filtered]"
    assert out["request"]["data"]["name"] == "Ada"
    assert out["extra"]["access_token"] == "[Filtered]"
    assert out["extra"]["path"] == "/health"


def test_init_sentry_is_noop_without_dsn(monkeypatch):
    from app.core import sentry as sentry_mod

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(sentry_mod, "_dsn", lambda: "")
    assert sentry_mod.init_sentry() is False


def test_production_500_via_http(app_client, monkeypatch):
    from main import app

    @app.get("/__ci_unhandled_boom")
    def _boom():
        raise RuntimeError("do-not-leak-this-secret")

    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()
    try:
        r = app_client.get("/__ci_unhandled_boom")
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal server error"}
        assert "do-not-leak-this-secret" not in r.text
        assert "error_type" not in r.json()
        assert "path" not in r.json()
    finally:
        monkeypatch.setenv("ENV", "test")
        get_settings.cache_clear()
