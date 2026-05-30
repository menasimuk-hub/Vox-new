"""Cronofy OAuth must use the configured regional data center."""

from __future__ import annotations

from app.services.scheduling_connection_service import cronofy_oauth_start


def test_cronofy_oauth_start_defaults_to_uk(monkeypatch):
    monkeypatch.setattr(
        "app.services.scheduling_connection_service._cronofy_platform_credentials",
        lambda db=None: ("test-client-id", "secret", "https://api.example.com/cb"),
    )
    monkeypatch.setattr(
        "app.services.scheduling_connection_service._cronofy_hosts",
        lambda db=None: ("app-uk.cronofy.com", "api-uk.cronofy.com"),
    )
    url = cronofy_oauth_start(org_id="org-1", db=None)
    assert url.startswith("https://app-uk.cronofy.com/oauth/authorize?")
    assert "client_id=test-client-id" in url
