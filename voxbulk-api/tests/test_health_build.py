"""Deploy verification endpoint — explicit marker flags."""


def test_health_build_returns_explicit_marker_flags(app_client):
    r = app_client.get("/health/build")
    assert r.status_code == 200
    data = r.json()
    assert data.get("webhook_build_marker") == "TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"
    assert "git_sha" in data
    assert "git_branch" in data
    assert data.get("boot_marker_present_on_disk") is True
    assert data.get("router_marker_present_on_disk") is True
    assert data.get("service_marker_present_on_disk") is True
    assert data.get("canonical_marker_present_on_disk") is True
    assert data.get("boot_marker_loaded") is True
    assert data.get("router_marker_loaded") is True
    assert data.get("service_marker_loaded") is True
    assert data.get("session_code_present_on_disk") is True
    assert data.get("session_code_loaded") is True
    assert data.get("session_persistence_fix_on_disk") is True
    assert data.get("session_persistence_fix_loaded") is True
    assert data.get("final_feedback_yes_no_loaded") is True
    assert data.get("final_feedback_yes_no_on_disk") is True
    assert data.get("final_feedback_yes_no_marker") == "WA_FINAL_FEEDBACK_YES_NO_ACTIVE"
    assert data.get("wa_test_session_handler", {}).get("handler") == (
        "SurveyBuilderTestService.start_wa_test_session"
    )
    assert data.get("deploy_ok") is True
    assert "wa_survey_debug_markers" not in data


def test_health_build_requires_token_when_configured(app_client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("HEALTH_SECRET_TOKEN", "test-health-token")
    get_settings.cache_clear()
    assert app_client.get("/health/build").status_code == 403
    assert app_client.get("/health/build", headers={"X-Health-Token": "wrong"}).status_code == 403
    assert app_client.get("/health/build", headers={"X-Health-Token": "test-health-token"}).status_code == 200
    assert (
        app_client.get("/health/build", headers={"Authorization": "Bearer test-health-token"}).status_code
        == 200
    )
    assert app_client.get("/health").status_code == 200
    get_settings.cache_clear()


def test_health_build_requires_token_from_settings(app_client, monkeypatch):
    """Token may live only in Settings/.env (not exported to os.environ)."""
    from app.core.config import get_settings

    monkeypatch.delenv("HEALTH_SECRET_TOKEN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "main.get_settings",
        lambda: type("S", (), {"health_secret_token": "settings-only-token"})(),
    )
    assert app_client.get("/health/build").status_code == 403
    assert (
        app_client.get("/health/build", headers={"X-Health-Token": "settings-only-token"}).status_code
        == 200
    )
    get_settings.cache_clear()
