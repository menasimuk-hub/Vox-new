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
