from __future__ import annotations

from app.services.telnyx_messaging_destinations_service import TelnyxMessagingDestinationsService
from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService


def test_ps_in_default_messaging_destinations():
    view = TelnyxMessagingDestinationsService.admin_view({})
    assert view["messaging_whitelisted_destinations"]["PS"] is True
    payload = TelnyxMessagingDestinationsService.to_telnyx_api_list(
        view["messaging_whitelisted_destinations"],
        allow_all=False,
    )
    assert "PS" in payload


def test_messaging_allow_all_sends_star():
    payload = TelnyxMessagingDestinationsService.to_telnyx_api_list({}, allow_all=True)
    assert payload == ["*"]


def test_ps_call_extra_when_enabled():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+970597567750",
        extras={"PS": {"code": "970", "allow_any_prefix": True}},
        extra_enabled={"PS": True},
        enabled={"GB": False, "AU": False, "CA": False, "USA": False},
    )
    assert result["allowed"] is True
    assert result["country"] == "PS"


def test_ps_call_extra_disabled():
    result = TelnyxPhoneAllowlistService.validate_phone(
        "+970597567750",
        extras={"PS": {"code": "970", "allow_any_prefix": True}},
        extra_enabled={"PS": False},
        enabled={"GB": False, "AU": False, "CA": False, "USA": False},
    )
    assert result["allowed"] is False
