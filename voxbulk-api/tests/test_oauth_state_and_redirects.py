from __future__ import annotations


def _seed_social_provider_config(db, provider: str):
    from app.services.provider_settings import ProviderSettingsService

    ProviderSettingsService.upsert_platform_config(
        db,
        provider=provider,
        is_enabled=True,
        config={
            "client_id": "client-id",
            "client_secret": "client-secret",
            "redirect_uri": f"http://127.0.0.1:8000/auth/oauth/{provider}/callback",
        },
    )


def test_oauth_start_sets_nonce_cookie_and_state_matches(app_client):
    from jose import jwt
    from urllib.parse import urlparse, parse_qs

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        _seed_social_provider_config(db, "google")

    r = app_client.get("/auth/oauth/google/start", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    qs = parse_qs(urlparse(loc).query)
    assert "state" in qs
    state = qs["state"][0]

    # Cookie should exist
    cookies = r.headers.get("set-cookie", "")
    assert "voxbulk_oauth_nonce" in cookies
    assert "voxbulk_oauth_provider" in cookies

    # Decode state and compare nonce
    payload = jwt.decode(state, "test-secret", algorithms=["HS256"])
    assert payload["provider"] == "google"
    assert payload.get("nonce")
    assert payload["nonce"] in cookies


def test_callback_rejects_missing_cookie(app_client, monkeypatch):
    from urllib.parse import quote

    # Avoid external calls if code ever reaches handler.
    async def fake_handle_callback(*args, **kwargs):
        raise AssertionError("Should not reach handle_callback when cookie missing")

    monkeypatch.setattr("app.routers.auth.SocialOAuthService.handle_callback", fake_handle_callback)
    r = app_client.get("/auth/oauth/google/callback?code=abc&state=bad", follow_redirects=False)
    assert r.status_code == 302
    assert "/signin?oauth_error=" in r.headers["location"]


def test_callback_rejects_state_provider_mismatch(app_client, monkeypatch):
    from jose import jwt
    from urllib.parse import urlparse, parse_qs

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        _seed_social_provider_config(db, "google")

    # Start to set cookies
    start = app_client.get("/auth/oauth/google/start", follow_redirects=False)
    assert start.status_code == 302

    # Build a state for google but hit apple callback
    state_raw = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    payload = jwt.decode(state_raw, "test-secret", algorithms=["HS256"])
    # Re-encode with same nonce/provider but we'll call a different provider route
    state = jwt.encode(payload, "test-secret", algorithm="HS256")

    async def fake_handle_callback(*args, **kwargs):
        raise AssertionError("Should not reach handle_callback when mismatch")

    monkeypatch.setattr("app.routers.auth.SocialOAuthService.handle_callback", fake_handle_callback)

    r = app_client.get(
        f"/auth/oauth/apple/callback?code=abc&state={state}",
        follow_redirects=False,
        cookies=start.cookies,
    )
    assert r.status_code == 302
    assert "/signin?oauth_error=" in r.headers["location"]


def test_callback_success_redirects_with_fragment(app_client, monkeypatch):
    from urllib.parse import urlparse

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        _seed_social_provider_config(db, "google")

    start = app_client.get("/auth/oauth/google/start", follow_redirects=False)
    assert start.status_code == 302
    loc = start.headers["location"]
    from urllib.parse import parse_qs, urlparse as _up

    state = parse_qs(_up(loc).query)["state"][0]

    async def fake_handle_callback(db, provider, code, state):
        return ("tok", "org1", "user1", False)

    monkeypatch.setattr("app.routers.auth.SocialOAuthService.handle_callback", fake_handle_callback)

    r = app_client.get(
        f"/auth/oauth/google/callback?code=abc&state={state}",
        follow_redirects=False,
        cookies=start.cookies,
    )
    assert r.status_code == 302
    redir = r.headers["location"]
    assert "/signin#" in redir
    assert "access_token=tok" in redir
    assert "org_id=org1" in redir
    assert "user_id=user1" in redir

