from __future__ import annotations

import pytest

from app.services.provider_settings import ProviderSettingsService


SANDBOX = {
    "access_token": "sandbox_tok_sandbox",
    "webhook_secret": "whsec_sandbox",
    "environment": "sandbox",
}

LIVE = {
    "access_token": "live_tok_live",
    "webhook_secret": "whsec_live",
    "environment": "live",
}


def test_legacy_sandbox_token_becomes_sandbox_bucket():
    out = ProviderSettingsService._validate_gocardless_config(SANDBOX, incoming=SANDBOX)
    assert out["environment"] == "sandbox"
    assert out["access_token_sandbox"] == SANDBOX["access_token"]
    assert out["webhook_secret_sandbox"] == SANDBOX["webhook_secret"]
    assert out["access_token"] == SANDBOX["access_token"]
    assert out["webhook_url"] == ProviderSettingsService.GOCARDLESS_WEBHOOK_URL


def test_http_webhook_is_upgraded_to_https():
    out = ProviderSettingsService._validate_gocardless_config(
        {**SANDBOX, "webhook_url": "http://api.voxbulk.com/webhooks/gocardless"},
        incoming={**SANDBOX, "webhook_url": "http://api.voxbulk.com/webhooks/gocardless"},
    )
    assert out["webhook_url"] == "https://api.voxbulk.com/webhooks/gocardless"


def test_localhost_http_webhook_becomes_production_https():
    out = ProviderSettingsService._validate_gocardless_config(
        {**SANDBOX, "webhook_url": "http://localhost:8000/webhooks/gocardless"},
        incoming={**SANDBOX, "webhook_url": "http://localhost:8000/webhooks/gocardless"},
    )
    assert out["webhook_url"] == ProviderSettingsService.GOCARDLESS_WEBHOOK_URL


def test_save_live_keeps_sandbox_token():
    sandbox = ProviderSettingsService._validate_gocardless_config(SANDBOX, incoming=SANDBOX)
    incoming = {**LIVE}
    out = ProviderSettingsService._validate_gocardless_config({**sandbox, **incoming}, incoming=incoming)
    assert out["environment"] == "live"
    assert out["access_token"] == LIVE["access_token"]
    assert out["access_token_sandbox"] == SANDBOX["access_token"]
    assert out["access_token_live"] == LIVE["access_token"]
    assert out["webhook_secret_sandbox"] == SANDBOX["webhook_secret"]
    assert out["webhook_secret_live"] == LIVE["webhook_secret"]


def test_switch_back_to_sandbox_without_reentering_token():
    sandbox = ProviderSettingsService._validate_gocardless_config(SANDBOX, incoming=SANDBOX)
    both = ProviderSettingsService._validate_gocardless_config(
        {**sandbox, **LIVE},
        incoming=LIVE,
    )
    out = ProviderSettingsService._validate_gocardless_config(
        {**both, "environment": "sandbox"},
        incoming={"environment": "sandbox"},
    )
    assert out["environment"] == "sandbox"
    assert out["access_token"] == SANDBOX["access_token"]
    assert out["access_token_live"] == LIVE["access_token"]


def test_live_environment_rejects_missing_live_token():
    sandbox = ProviderSettingsService._validate_gocardless_config(SANDBOX, incoming=SANDBOX)
    with pytest.raises(ValueError, match="Live access token is required"):
        ProviderSettingsService._validate_gocardless_config(
            {**sandbox, "environment": "live"},
            incoming={"environment": "live"},
        )


def test_credentials_for_sandbox_while_live_is_active():
    sandbox = ProviderSettingsService._validate_gocardless_config(SANDBOX, incoming=SANDBOX)
    both = ProviderSettingsService._validate_gocardless_config({**sandbox, **LIVE}, incoming=LIVE)
    creds = ProviderSettingsService.gocardless_credentials_for_environment(both, "sandbox")
    assert creds["environment"] == "sandbox"
    assert creds["access_token"] == SANDBOX["access_token"]
    live_creds = ProviderSettingsService.gocardless_credentials_for_environment(both, "live")
    assert live_creds["environment"] == "live"
    assert live_creds["access_token"] == LIVE["access_token"]
    assert both["environment"] == "live"
