from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.services.provider_settings import ProviderSettingsService
from app.services.stripe_payment_service import StripePaymentService, StripeProviderError


SANDBOX = {
    "secret_key": "sk_test_sandbox",
    "publishable_key": "pk_test_sandbox",
    "webhook_secret": "whsec_sandbox",
}

LIVE = {
    "secret_key": "sk_live_livekey",
    "publishable_key": "pk_live_livekey",
    "webhook_secret": "whsec_live",
}


def test_legacy_test_keys_become_sandbox_bucket():
    out = ProviderSettingsService._validate_stripe_config(
        {**SANDBOX, "environment": "test"},
        incoming={**SANDBOX, "environment": "test"},
    )
    assert out["environment"] == "sandbox"
    assert out["secret_key_sandbox"] == SANDBOX["secret_key"]
    assert out["publishable_key_sandbox"] == SANDBOX["publishable_key"]
    assert out["webhook_secret_sandbox"] == SANDBOX["webhook_secret"]
    assert out["secret_key"] == SANDBOX["secret_key"]
    assert not out.get("secret_key_live")


def test_save_live_keeps_sandbox_keys():
    sandbox = ProviderSettingsService._validate_stripe_config(SANDBOX, incoming=SANDBOX)
    incoming = {"environment": "live", **LIVE}
    out = ProviderSettingsService._validate_stripe_config({**sandbox, **incoming}, incoming=incoming)
    assert out["environment"] == "live"
    assert out["secret_key"] == LIVE["secret_key"]
    assert out["secret_key_sandbox"] == SANDBOX["secret_key"]
    assert out["secret_key_live"] == LIVE["secret_key"]
    assert out["publishable_key_sandbox"] == SANDBOX["publishable_key"]
    assert out["publishable_key_live"] == LIVE["publishable_key"]
    assert out["webhook_secret_sandbox"] == SANDBOX["webhook_secret"]
    assert out["webhook_secret_live"] == LIVE["webhook_secret"]


def test_switch_back_to_sandbox_without_reentering_keys():
    sandbox = ProviderSettingsService._validate_stripe_config(SANDBOX, incoming=SANDBOX)
    both = ProviderSettingsService._validate_stripe_config(
        {**sandbox, "environment": "live", **LIVE},
        incoming={"environment": "live", **LIVE},
    )
    out = ProviderSettingsService._validate_stripe_config(
        {**both, "environment": "sandbox"},
        incoming={"environment": "sandbox"},
    )
    assert out["environment"] == "sandbox"
    assert out["secret_key"] == SANDBOX["secret_key"]
    assert out["publishable_key"] == SANDBOX["publishable_key"]
    assert out["webhook_secret"] == SANDBOX["webhook_secret"]
    assert out["secret_key_live"] == LIVE["secret_key"]


def test_live_environment_rejects_missing_live_keys():
    sandbox = ProviderSettingsService._validate_stripe_config(SANDBOX, incoming=SANDBOX)
    with pytest.raises(ValueError, match="Live secret key is required"):
        ProviderSettingsService._validate_stripe_config(
            {**sandbox, "environment": "live"},
            incoming={"environment": "live"},
        )


def test_apply_active_credentials_does_not_mix_envs():
    cfg = ProviderSettingsService.apply_stripe_active_credentials(
        {
            "environment": "live",
            "secret_key": SANDBOX["secret_key"],
            "publishable_key": SANDBOX["publishable_key"],
            "secret_key_sandbox": SANDBOX["secret_key"],
            "publishable_key_sandbox": SANDBOX["publishable_key"],
        }
    )
    assert cfg["environment"] == "live"
    assert cfg["secret_key"] == ""
    assert cfg["publishable_key"] == ""


def test_webhook_accepts_inactive_environment_secret(monkeypatch):
    payload = json.dumps({"id": "evt_1", "type": "ping"}).encode("utf-8")
    ts = str(int(time.time()))
    signed = f"{ts}.{payload.decode('utf-8')}"
    digest = hmac.new(b"whsec_sandbox", signed.encode("utf-8"), hashlib.sha256).hexdigest()

    monkeypatch.setattr(
        StripePaymentService,
        "get_config",
        staticmethod(
            lambda _db: {
                "environment": "live",
                "webhook_secret": "whsec_live",
                "webhook_secret_live": "whsec_live",
                "webhook_secret_sandbox": "whsec_sandbox",
                "secret_key": "sk_live_x",
            }
        ),
    )
    event = StripePaymentService.verify_webhook_signature(
        db=None, payload=payload, signature_header=f"t={ts},v1={digest}"
    )
    assert event["id"] == "evt_1"

    with pytest.raises(StripeProviderError, match="signature mismatch"):
        StripePaymentService.verify_webhook_signature(
            db=None, payload=payload, signature_header=f"t={ts},v1={'0' * 64}"
        )
