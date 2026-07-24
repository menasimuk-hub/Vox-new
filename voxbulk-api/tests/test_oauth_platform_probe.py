"""Unit tests for OAuth platform probe helpers."""

from app.services.oauth_platform_test_service import oauth_probe_credentials_accepted


def test_oauth_probe_credentials_accepted_reasons():
    assert oauth_probe_credentials_accepted("invalid_grant_expected") is True
    assert oauth_probe_credentials_accepted("unexpected_but_nonfatal") is True
    assert oauth_probe_credentials_accepted("invalid_grant") is True
    assert oauth_probe_credentials_accepted("invalid_code") is True
    assert oauth_probe_credentials_accepted("client_not_found") is False
    assert oauth_probe_credentials_accepted("invalid_secret") is False
    assert oauth_probe_credentials_accepted("provider_error") is False
    assert oauth_probe_credentials_accepted(None) is False
