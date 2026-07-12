from __future__ import annotations

from app.services.telnyx_messaging_destinations_service import TelnyxMessagingDestinationsService
from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService


def test_default_allow_all_for_whatsapp():
    view = TelnyxMessagingDestinationsService.admin_view({})
    assert view["messaging_allow_all_destinations"] is True
    assert view["messaging_blocked_destinations"] == {}
    assert view["whatsapp_telnyx_payload"] == ["*"]
    assert TelnyxMessagingDestinationsService.whatsapp_telnyx_payload() == ["*"]


def test_sanitize_forces_allow_all_and_keeps_blocks():
    out = TelnyxMessagingDestinationsService.sanitize_config(
        {
            "messaging_allow_all_destinations": False,
            "messaging_blocked_destinations": {"EG": True, "XX": False},
        }
    )
    assert out["messaging_allow_all_destinations"] is True
    assert out["messaging_blocked_destinations"] == {"EG": True}


def test_blocked_iso_rejected():
    check = TelnyxMessagingDestinationsService.check_whatsapp_destination(
        "+201012345678",
        cfg={"messaging_blocked_destinations": {"EG": True}},
    )
    assert check["allowed"] is False
    assert check["country"] == "EG"
    assert "blocked" in str(check["reason"]).lower()


def test_unblocked_country_allowed():
    check = TelnyxMessagingDestinationsService.check_whatsapp_destination(
        "+447700900123",
        cfg={"messaging_blocked_destinations": {"EG": True}},
    )
    assert check["allowed"] is True
    assert check["country"] == "GB"


def test_sms_payload_from_call_allowlist():
    payload = TelnyxMessagingDestinationsService.sms_destinations_from_call_allowlist(
        {
            "phone_allowlist_enabled": {"GB": True, "AU": False, "CA": True, "USA": True},
            "phone_allowlist_extra": {"PS": {"code": "970", "allow_any_prefix": True}},
            "phone_allowlist_extra_enabled": {"PS": True},
        }
    )
    assert payload == ["CA", "GB", "PS", "US"]


def test_sms_payload_fallback_when_none_enabled():
    payload = TelnyxMessagingDestinationsService.sms_destinations_from_call_allowlist(
        {
            "phone_allowlist_enabled": {"GB": False, "AU": False, "CA": False, "USA": False},
            "phone_allowlist_extra_enabled": {},
        }
    )
    assert payload == ["GB"]


def test_whatsapp_telnyx_payload_is_star():
    assert TelnyxMessagingDestinationsService.whatsapp_telnyx_payload() == ["*"]


def test_collect_profiles_by_channel_shared_prefers_wa():
    shared = "11111111-1111-1111-1111-111111111111"
    wa_only = "22222222-2222-2222-2222-222222222222"
    sms_only = "33333333-3333-3333-3333-333333333333"
    wa_ids, sms_ids = TelnyxMessagingDestinationsService.collect_profiles_by_channel(
        {
            "whatsapp_messaging_profile_id": shared,
            "messaging_profile_id": shared,
            "whatsapp_messaging_profile_id_2": wa_only,
            "sms_messaging_profile_id_2": sms_only,
        }
    )
    assert shared in wa_ids
    assert wa_only in wa_ids
    assert sms_only in sms_ids
    assert shared not in sms_ids


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
