from __future__ import annotations

import pytest

from app.services.telnyx_phone_allowlist_service import (
    DEFAULT_PHONE_ALLOWLIST_ENABLED,
    TelnyxPhoneAllowlistService,
)


def test_gb_mobile_allowed():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+447700900123",
        enabled=DEFAULT_PHONE_ALLOWLIST_ENABLED,
    )
    assert result["allowed"] is True
    assert result["country"] == "GB"
    assert result["line_type"] == "mobile"


def test_gb_invalid_prefix_blocked():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+446123456789",
        enabled=DEFAULT_PHONE_ALLOWLIST_ENABLED,
    )
    assert result["allowed"] is False
    assert "allow list" in str(result["reason"]).lower()


def test_usa_nanp_allowed():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+12125551212",
        enabled=DEFAULT_PHONE_ALLOWLIST_ENABLED,
    )
    assert result["allowed"] is True
    assert result["country"] == "USA"


def test_canada_area_code():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+14165551234",
        enabled=DEFAULT_PHONE_ALLOWLIST_ENABLED,
    )
    assert result["allowed"] is True
    assert result["country"] == "CA"


def test_disabled_country():
    enabled = dict(DEFAULT_PHONE_ALLOWLIST_ENABLED)
    enabled["GB"] = False
    result = TelnyxPhoneAllowlistService.validate_phone("+447700900123", enabled=enabled)
    assert result["allowed"] is False
    assert "disabled" in str(result["reason"]).lower()


def test_removed_core_country_disabled_on_load():
    allowlist, enabled, extras, extra_enabled, removed = TelnyxPhoneAllowlistService.load_from_telnyx_config(
        {"phone_allowlist_removed": ["AU", "CA"]}
    )
    assert removed == ["AU", "CA"]
    assert enabled["AU"] is False
    assert enabled["CA"] is False
    assert enabled["GB"] is True
    assert allowlist["GB"]["code"] == "44"
    del extras, extra_enabled


def test_empty_extra_does_not_reseed_ps():
    _a, _e, extras, extra_enabled, _r = TelnyxPhoneAllowlistService.load_from_telnyx_config(
        {"phone_allowlist_extra": {}, "phone_allowlist_extra_enabled": {}}
    )
    assert extras == {}
    assert extra_enabled == {}


def test_missing_extra_key_seeds_ps():
    _a, _e, extras, extra_enabled, _r = TelnyxPhoneAllowlistService.load_from_telnyx_config({})
    assert "PS" in extras
    assert extras["PS"]["code"] == "970"
    assert extra_enabled.get("PS") is False
