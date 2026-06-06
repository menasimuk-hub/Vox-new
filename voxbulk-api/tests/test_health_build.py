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
    assert data.get("deploy_ok") is True
    assert "wa_survey_debug_markers" not in data
