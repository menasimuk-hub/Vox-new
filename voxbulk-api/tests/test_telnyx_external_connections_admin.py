from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Telnyx External Org")
        db.add(org)
        db.flush()
        user = User(
            email="telnyx_external_admin@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        email = user.email
    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _save_telnyx_minimal(app_client, headers):
    res = app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "KEY" + "a" * 55,
                "connection_id": "conn-123",
                "default_outbound_number": "+15550001111",
                "voice_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/voice",
                "status_callback_url": "https://api.voxbulk.com/telnyx/webhooks/status",
                "messaging_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/messages",
            },
        },
        headers=headers,
    )
    assert res.status_code == 200


def test_admin_telnyx_zoom_oauth_save_endpoint(app_client):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-zoom-test",
            "client_id": "client-zoom-test",
            "client_secret": "secret-zoom-test",
            "base_url": "https://api.zoom.us/v2",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["config"]["zoom_account_id"] == "acct-zoom-test"
    assert body["config"]["zoom_client_id"] == "client-zoom-test"
    assert body["secret_set"]["zoom_client_secret"] is True

    from app.core.database import get_sessionmaker
    from app.services.provider_settings import ProviderSettingsService
    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "acct-zoom-test"
        assert cfg["client_id"] == "client-zoom-test"
        telnyx_cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        assert str(telnyx_cfg.get("zoom_client_secret") or "") == "secret-zoom-test"


def test_zoom_secret_set_on_get_after_save(app_client):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-get-test",
            "client_id": "client-get-test",
            "client_secret": "secret-get-test",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    get_res = app_client.get("/admin/integrations/telnyx", headers=headers)
    assert get_res.status_code == 200, get_res.text
    body = get_res.json()
    assert body["secret_set"]["zoom_client_secret"] is True
    assert body["config"]["zoom_account_id"] == "acct-get-test"
    assert body["config"]["zoom_client_id"] == "client-get-test"


def test_zoom_secret_survives_main_telnyx_resave(app_client):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    zoom_res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-zoom-persist",
            "client_id": "client-zoom-persist",
            "client_secret": "secret-zoom-persist",
            "base_url": "https://api.zoom.us/v2",
        },
        headers=headers,
    )
    assert zoom_res.status_code == 200, zoom_res.text

    telnyx_res = app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "connection_id": "conn-updated-999",
                "voice_api_application_id": "conn-updated-999",
                "default_outbound_number": "+15550001111",
                "voice_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/voice",
                "status_callback_url": "https://api.voxbulk.com/telnyx/webhooks/status",
                "messaging_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/messages",
            },
        },
        headers=headers,
    )
    assert telnyx_res.status_code == 200, telnyx_res.text
    body = telnyx_res.json()
    assert body["secret_set"]["zoom_client_secret"] is True
    assert body["config"]["connection_id"] == "conn-updated-999"

    from app.core.database import get_sessionmaker
    from app.services.provider_settings import ProviderSettingsService

    with get_sessionmaker()() as db:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        assert str(cfg.get("zoom_client_secret") or "") == "secret-zoom-persist"
        assert str(cfg.get("zoom_account_id") or "") == "acct-zoom-persist"


def test_zoom_secret_readable_after_new_db_session(app_client):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-restart-test",
            "client_id": "client-restart-test",
            "client_secret": "secret-restart-test",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    from app.core.database import get_sessionmaker
    from app.services.provider_settings import ProviderSettingsService
    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        assert str(cfg.get("zoom_client_secret") or "") == "secret-restart-test"
        zoom_cfg = ZoomService._config(db)
        assert zoom_cfg["client_secret"] == "secret-restart-test"
        assert zoom_cfg["account_id"] == "acct-restart-test"


def test_zoom_survives_main_telnyx_resave_and_restart_session(app_client):
    """Zoom creds from /telnyx/zoom-oauth must survive main Telnyx save + fresh DB session."""
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-after-resave",
            "client_id": "client-after-resave",
            "client_secret": "secret-after-resave",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    telnyx_res = app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "connection_id": "conn-resave-777",
                "voice_api_application_id": "conn-resave-777",
                "default_outbound_number": "+15550001111",
                "voice_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/voice",
                "status_callback_url": "https://api.voxbulk.com/telnyx/webhooks/status",
                "messaging_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/messages",
            },
        },
        headers=headers,
    )
    assert telnyx_res.status_code == 200, telnyx_res.text

    from app.core.database import get_sessionmaker
    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "acct-after-resave"
        assert cfg["client_id"] == "client-after-resave"
        assert cfg["client_secret"] == "secret-after-resave"


def test_telnyx_zoom_row_wins_over_legacy_standalone_zoom_row(app_client):
    """Runtime reads Telnyx zoom_* only; legacy provider=zoom row must not override."""
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    from app.core.database import get_sessionmaker
    from app.services.provider_settings import ProviderSettingsService

    with get_sessionmaker()() as db:
        ProviderSettingsService.upsert_platform_config(
            db,
            provider="zoom",
            is_enabled=True,
            config={
                "account_id": "legacy-acct",
                "client_id": "legacy-client",
                "client_secret": "legacy-secret",
            },
        )

    fresh = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "fresh-acct",
            "client_id": "fresh-client",
            "client_secret": "fresh-secret",
        },
        headers=headers,
    )
    assert fresh.status_code == 200, fresh.text

    with get_sessionmaker()() as db:
        from app.services.zoom_service import ZoomService

        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "fresh-acct"
        assert cfg["client_id"] == "fresh-client"
        assert cfg["client_secret"] == "fresh-secret"


def test_env_fallback_not_used_when_telnyx_has_zoom(app_client, monkeypatch):
    """Telnyx DB credentials must win over .env when telnyx.zoom_* is populated."""
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "env-acct")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "env-client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "env-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()

    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "db-acct",
            "client_id": "db-client",
            "client_secret": "db-secret",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text

    from app.core.database import get_sessionmaker
    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "db-acct"
        assert cfg["client_id"] == "db-client"
        assert cfg["client_secret"] == "db-secret"

    get_settings.cache_clear()


def test_admin_telnyx_zoom_external_connection_create_and_test(app_client, monkeypatch):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    zoom_res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-meta-patch",
            "client_id": "client-meta-patch",
            "client_secret": "secret-meta-patch",
        },
        headers=headers,
    )
    assert zoom_res.status_code == 200, zoom_res.text

    def fake_telnyx_request(_db, method, path, *, json_body=None, params=None, timeout=30.0):
        _ = timeout
        m = str(method).upper()
        if m == "POST" and path == "/external_connections":
            assert json_body["external_sip_connection"] == "zoom"
            assert json_body["outbound"]["outbound_voice_profile_id"] == "1911630617284445511"
            return (
                201,
                {
                    "data": {
                        "id": "zoom-conn-1",
                        "external_sip_connection": "zoom",
                        "active": True,
                        "credential_active": True,
                    }
                },
                "",
            )
        if m == "GET" and path == "/external_connections/zoom-conn-1":
            return (
                200,
                {
                    "data": {
                        "id": "zoom-conn-1",
                        "external_sip_connection": "zoom",
                        "active": True,
                        "credential_active": True,
                    }
                },
                "",
            )
        raise AssertionError(f"Unexpected Telnyx call: {m} {path} params={params} body={json_body}")

    monkeypatch.setattr(
        "app.services.telnyx_external_connection_service._telnyx_request",
        fake_telnyx_request,
    )

    created = app_client.post(
        "/admin/integrations/telnyx/zoom/create-connection",
        json={"outbound_voice_profile_id": "1911630617284445511"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True
    assert body["connection"]["id"] == "zoom-conn-1"

    tested = app_client.post(
        "/admin/integrations/telnyx/zoom/test-connection",
        json={"connection_id": "zoom-conn-1"},
        headers=headers,
    )
    assert tested.status_code == 200
    result = tested.json()
    assert result["ok"] is True
    assert result["connection"]["id"] == "zoom-conn-1"

    cfg = app_client.get("/admin/integrations/telnyx", headers=headers)
    assert cfg.status_code == 200
    data = cfg.json()
    assert data["config"]["zoom_external_connection_id"] == "zoom-conn-1"
    assert data["config"]["zoom_outbound_voice_profile_id"] == "1911630617284445511"
    assert data["secret_set"]["zoom_client_secret"] is True

    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        resolved = ZoomService._config(db)
        assert resolved["client_secret"] == "secret-meta-patch"


def test_zoom_secret_survives_connection_metadata_patch(app_client, monkeypatch):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    zoom_res = app_client.put(
        "/admin/integrations/telnyx/zoom-oauth",
        json={
            "account_id": "acct-conn-patch",
            "client_id": "client-conn-patch",
            "client_secret": "secret-conn-patch",
        },
        headers=headers,
    )
    assert zoom_res.status_code == 200, zoom_res.text

    def fake_telnyx_request(_db, method, path, *, json_body=None, params=None, timeout=30.0):
        _ = timeout
        m = str(method).upper()
        if m == "POST" and path == "/external_connections":
            return (
                201,
                {
                    "data": {
                        "id": "zoom-conn-patch",
                        "external_sip_connection": "zoom",
                        "active": True,
                        "credential_active": True,
                    }
                },
                "",
            )
        raise AssertionError(f"Unexpected Telnyx call: {m} {path}")

    monkeypatch.setattr(
        "app.services.telnyx_external_connection_service._telnyx_request",
        fake_telnyx_request,
    )

    created = app_client.post(
        "/admin/integrations/telnyx/zoom/create-connection",
        json={"outbound_voice_profile_id": "1911630617284445511"},
        headers=headers,
    )
    assert created.status_code == 200, created.text

    get_res = app_client.get("/admin/integrations/telnyx", headers=headers)
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["secret_set"]["zoom_client_secret"] is True

    from app.services.zoom_service import ZoomService

    with get_sessionmaker()() as db:
        resolved = ZoomService._config(db)
        assert resolved["account_id"] == "acct-conn-patch"
        assert resolved["client_secret"] == "secret-conn-patch"


def test_admin_telnyx_microsoft_teams_create_and_test(app_client, monkeypatch):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    def fake_telnyx_request(_db, method, path, *, json_body=None, params=None, timeout=30.0):
        _ = (json_body, timeout)
        m = str(method).upper()
        if m == "POST" and path == "/operator_connect/actions/refresh":
            return 202, {"success": True, "message": "refresh queued"}, ""
        if m == "GET" and path == "/external_connections":
            if (params or {}).get("filter[external_sip_connection]") == "operator_connect":
                return (
                    200,
                    {
                        "data": [
                            {
                                "id": "teams-conn-1",
                                "external_sip_connection": "operator_connect",
                                "active": True,
                                "credential_active": True,
                            }
                        ]
                    },
                    "",
                )
            return 200, {"data": []}, ""
        raise AssertionError(f"Unexpected Telnyx call: {m} {path} params={params}")

    monkeypatch.setattr(
        "app.services.telnyx_external_connection_service._telnyx_request",
        fake_telnyx_request,
    )

    created = app_client.post(
        "/admin/integrations/telnyx/microsoft-teams/create-connection",
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True
    assert body["snapshot"]["connection_count"] == 1

    tested = app_client.post(
        "/admin/integrations/telnyx/microsoft-teams/test-connection",
        headers=headers,
    )
    assert tested.status_code == 200
    result = tested.json()
    assert result["ok"] is True
    assert result["connection_count"] == 1
    assert result["active_connection_count"] == 1

    cfg = app_client.get("/admin/integrations/telnyx", headers=headers)
    assert cfg.status_code == 200
    assert cfg.json()["config"]["teams_external_connection_id"] == "teams-conn-1"


def test_admin_telnyx_zoom_profiles_and_create_uses_config_fallback(app_client, monkeypatch):
    headers = _admin_headers(app_client)
    _save_telnyx_minimal(app_client, headers)

    def fake_telnyx_request(_db, method, path, *, json_body=None, params=None, timeout=30.0):
        _ = timeout
        m = str(method).upper()
        if m == "GET" and path == "/outbound_voice_profiles":
            return (
                200,
                {
                    "data": [
                        {"id": "ovp-1", "name": "Primary UK", "active": True},
                        {"id": "ovp-2", "name": "Backup", "active": True},
                    ]
                },
                "",
            )
        if m == "POST" and path == "/external_connections":
            assert json_body["external_sip_connection"] == "zoom"
            # falls back to telnyx connection_id from saved config when payload omits outbound_voice_profile_id
            assert json_body["outbound"]["outbound_voice_profile_id"] == "conn-123"
            return (
                201,
                {
                    "data": {
                        "id": "zoom-conn-fallback",
                        "external_sip_connection": "zoom",
                        "active": True,
                        "credential_active": True,
                    }
                },
                "",
            )
        raise AssertionError(f"Unexpected Telnyx call: {m} {path} params={params} body={json_body}")

    monkeypatch.setattr(
        "app.services.telnyx_external_connection_service._telnyx_request",
        fake_telnyx_request,
    )

    listed = app_client.get(
        "/admin/integrations/telnyx/zoom/outbound-voice-profiles",
        headers=headers,
    )
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["ok"] is True
    assert len(payload["profiles"]) == 2
    assert payload["selected_outbound_voice_profile_id"] == "conn-123"

    created = app_client.post(
        "/admin/integrations/telnyx/zoom/create-connection",
        json={},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True
    assert body["connection"]["id"] == "zoom-conn-fallback"
