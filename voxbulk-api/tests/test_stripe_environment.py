from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock

import pytest

from app.services.provider_settings import ProviderSettingsService
from app.services.stripe_payment_service import StripeConfigError, StripePaymentService, StripeProviderError


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


def _both_buckets():
    sandbox = ProviderSettingsService._validate_stripe_config(SANDBOX, incoming=SANDBOX)
    return ProviderSettingsService._validate_stripe_config(
        {**sandbox, "environment": "live", **LIVE},
        incoming={"environment": "live", **LIVE},
    )


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
    out = _both_buckets()
    assert out["environment"] == "live"
    assert out["secret_key"] == LIVE["secret_key"]
    assert out["secret_key_sandbox"] == SANDBOX["secret_key"]
    assert out["secret_key_live"] == LIVE["secret_key"]


def test_switch_sandbox_when_both_buckets_populated():
    both = _both_buckets()
    out = ProviderSettingsService._validate_stripe_config(
        {**both, "environment": "sandbox"},
        incoming={"environment": "sandbox"},
    )
    assert out["environment"] == "sandbox"
    assert out["secret_key"] == SANDBOX["secret_key"]
    assert out["publishable_key"] == SANDBOX["publishable_key"]
    assert out["webhook_secret"] == SANDBOX["webhook_secret"]
    assert out["secret_key_live"] == LIVE["secret_key"]


def test_switch_live_when_both_buckets_populated():
    both = _both_buckets()
    sandbox_active = ProviderSettingsService._validate_stripe_config(
        {**both, "environment": "sandbox"},
        incoming={"environment": "sandbox"},
    )
    out = ProviderSettingsService._validate_stripe_config(
        {**sandbox_active, "environment": "live"},
        incoming={"environment": "live"},
    )
    assert out["environment"] == "live"
    assert out["secret_key"] == LIVE["secret_key"]
    assert out["secret_key_sandbox"] == SANDBOX["secret_key"]


def test_incomplete_sandbox_bucket_fails_loudly_no_live_fallback():
    live_only = ProviderSettingsService._validate_stripe_config(LIVE, incoming=LIVE)
    assert live_only["environment"] == "live"
    with pytest.raises(ValueError, match="Sandbox secret key is required"):
        ProviderSettingsService._validate_stripe_config(
            {**live_only, "environment": "sandbox"},
            incoming={"environment": "sandbox"},
        )


def test_apply_never_falls_back_to_stale_top_level_or_other_mode():
    cfg = ProviderSettingsService.apply_stripe_active_credentials(
        {
            "environment": "sandbox",
            "secret_key": LIVE["secret_key"],
            "publishable_key": LIVE["publishable_key"],
            "webhook_secret": LIVE["webhook_secret"],
            "secret_key_live": LIVE["secret_key"],
            "publishable_key_live": LIVE["publishable_key"],
            "webhook_secret_live": LIVE["webhook_secret"],
        }
    )
    assert cfg["environment"] == "sandbox"
    assert cfg["secret_key"] == ""
    assert cfg["publishable_key"] == ""
    assert cfg["webhook_secret"] == ""


def test_get_config_refuses_incomplete_active_bucket(monkeypatch):
    both = _both_buckets()
    incomplete = {**both, "environment": "sandbox"}
    incomplete.pop("secret_key_sandbox", None)
    incomplete["secret_key"] = LIVE["secret_key"]

    monkeypatch.setattr(
        ProviderSettingsService,
        "get_platform_config_decrypted",
        staticmethod(lambda _db, provider="stripe": (incomplete, True)),
    )
    with pytest.raises(StripeConfigError, match="incomplete|Sandbox secret key"):
        StripePaymentService.get_config(db=None)


def test_test_connection_does_not_change_active_mode(monkeypatch):
    both = _both_buckets()
    store = {"cfg": dict(both)}

    def fake_decrypt(_db, provider="stripe"):
        return dict(store["cfg"]), True

    monkeypatch.setattr(
        ProviderSettingsService,
        "get_platform_config_decrypted",
        staticmethod(fake_decrypt),
    )

    def fake_request(secret, method, path, data=None, mode=None):
        return {"livemode": secret.startswith("sk_live_"), "available": [{"currency": "gbp"}]}

    monkeypatch.setattr(StripePaymentService, "_request_with_secret", staticmethod(fake_request))

    before = store["cfg"]["environment"]
    result = StripePaymentService.test_connection(db=None, environment="sandbox")
    assert result["environment"] == "sandbox"
    assert result["active_environment"] == "live"
    assert result["active_environment_unchanged"] is True
    assert store["cfg"]["environment"] == before == "live"


def test_webhook_accepts_only_active_mode_secret(monkeypatch):
    both = _both_buckets()
    monkeypatch.setattr(
        StripePaymentService,
        "get_config",
        staticmethod(lambda _db: ProviderSettingsService.apply_stripe_active_credentials(both)),
    )
    payload = json.dumps({"id": "evt_1", "type": "ping", "livemode": True}).encode("utf-8")
    ts = str(int(time.time()))
    signed = f"{ts}.{payload.decode('utf-8')}"
    live_digest = hmac.new(b"whsec_live", signed.encode("utf-8"), hashlib.sha256).hexdigest()
    sandbox_digest = hmac.new(b"whsec_sandbox", signed.encode("utf-8"), hashlib.sha256).hexdigest()

    event = StripePaymentService.verify_webhook_signature(
        db=None, payload=payload, signature_header=f"t={ts},v1={live_digest}"
    )
    assert event["id"] == "evt_1"

    with pytest.raises(StripeProviderError, match="signature mismatch"):
        StripePaymentService.verify_webhook_signature(
            db=None, payload=payload, signature_header=f"t={ts},v1={sandbox_digest}"
        )


def test_webhook_rejects_livemode_mismatch(monkeypatch):
    both = _both_buckets()
    monkeypatch.setattr(
        StripePaymentService,
        "get_config",
        staticmethod(lambda _db: ProviderSettingsService.apply_stripe_active_credentials(both)),
    )
    payload = json.dumps({"id": "evt_2", "type": "ping", "livemode": False}).encode("utf-8")
    ts = str(int(time.time()))
    signed = f"{ts}.{payload.decode('utf-8')}"
    live_digest = hmac.new(b"whsec_live", signed.encode("utf-8"), hashlib.sha256).hexdigest()
    with pytest.raises(StripeProviderError, match="livemode"):
        StripePaymentService.verify_webhook_signature(
            db=None, payload=payload, signature_header=f"t={ts},v1={live_digest}"
        )


def test_active_mode_snapshot_reads_get_config(monkeypatch):
    both = _both_buckets()
    monkeypatch.setattr(
        StripePaymentService,
        "get_config",
        staticmethod(lambda _db: ProviderSettingsService.apply_stripe_active_credentials(both)),
    )
    snap = StripePaymentService.active_mode_snapshot(db=None)
    assert snap["environment"] == "live"
    assert snap["livemode"] is True
    assert snap["secret_key_prefix"].startswith("sk_live_")
    assert snap["source"] == "StripePaymentService.get_config"


def test_checkout_response_includes_mode_fields(monkeypatch):
    both = _both_buckets()
    cfg = ProviderSettingsService.apply_stripe_active_credentials(both)
    monkeypatch.setattr(StripePaymentService, "get_config", staticmethod(lambda _db: cfg))
    monkeypatch.setattr(
        StripePaymentService,
        "_request",
        staticmethod(lambda _db, method, path, data=None: {
            "id": "pi_x",
            "client_secret": "sec",
            "amount": 1000,
            "status": "requires_payment_method",
        }),
    )
    monkeypatch.setattr(
        "app.services.billing_currency.resolve_org_currency",
        lambda _db, _org, persist=False: "gbp",
    )
    org = MagicMock()
    org.id = "org1"
    org.name = "Test"
    out = StripePaymentService._create_payment_intent(
        None,
        org,
        amount_minor=1000,
        kind="wallet_topup",
        description="test",
        metadata_extra=None,
    )
    assert out["environment"] == "live"
    assert out["livemode"] is True
    assert out["stripe_mode"] == "live"
