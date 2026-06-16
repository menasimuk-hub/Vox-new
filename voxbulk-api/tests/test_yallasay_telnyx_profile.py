"""Yallasay Telnyx line — messaging profile ID validation."""

from __future__ import annotations

from unittest.mock import patch

from app.services.provider_settings import ProviderSettingsService
from app.services.yallasay_telnyx_line import get_yallasay_line_config

VALID_UUID = "40019e47-a9de-45bb-8e93-9e1abb3521cc"
YALLASAY_PHONE = "+447822002099"


def test_sanitize_messaging_profile_id_rejects_phone_number():
    assert ProviderSettingsService.sanitize_messaging_profile_id(
        YALLASAY_PHONE, field="sms_messaging_profile_id_2"
    ) == ""


def test_sanitize_messaging_profile_id_accepts_uuid():
    assert (
        ProviderSettingsService.sanitize_messaging_profile_id(VALID_UUID, field="sms_messaging_profile_id_2")
        == VALID_UUID
    )


def test_looks_like_phone_not_profile():
    assert ProviderSettingsService.looks_like_phone_not_profile(YALLASAY_PHONE) is True
    assert ProviderSettingsService.looks_like_phone_not_profile(VALID_UUID) is False
    assert ProviderSettingsService.looks_like_phone_not_profile("") is False


def test_validate_telnyx_config_clears_phone_as_yallasay_profile():
    cfg = ProviderSettingsService._validate_telnyx_config(
        {
            "sms_from_2": YALLASAY_PHONE,
            "sms_messaging_profile_id_2": YALLASAY_PHONE,
            "whatsapp_messaging_profile_id_2": YALLASAY_PHONE,
            "whatsapp_messaging_profile_id": VALID_UUID,
        }
    )
    assert cfg["sms_messaging_profile_id_2"] == ""
    assert cfg["whatsapp_messaging_profile_id_2"] == ""
    assert cfg["whatsapp_messaging_profile_id"] == VALID_UUID


def test_get_yallasay_line_config_no_survey_profile_fallback():
    telnyx_cfg = {
        "sms_from_2": YALLASAY_PHONE,
        "sms_messaging_profile_id_2": YALLASAY_PHONE,
        "whatsapp_messaging_profile_id": VALID_UUID,
        "messaging_profile_id": VALID_UUID,
    }

    class _FakeDb:
        pass

    with patch(
        "app.services.yallasay_telnyx_line.ProviderSettingsService.get_platform_config_decrypted",
        return_value=(telnyx_cfg, True),
    ):
        line = get_yallasay_line_config(_FakeDb())

    assert line["whatsapp_messaging_profile_id"] is None
    assert line["messaging_profile_id"] is None


def test_get_yallasay_line_config_uses_valid_yallasay_profile():
    telnyx_cfg = {
        "sms_from_2": YALLASAY_PHONE,
        "whatsapp_from_2": YALLASAY_PHONE,
        "sms_messaging_profile_id_2": VALID_UUID,
        "whatsapp_messaging_profile_id_2": VALID_UUID,
    }

    class _FakeDb:
        pass

    with patch(
        "app.services.yallasay_telnyx_line.ProviderSettingsService.get_platform_config_decrypted",
        return_value=(telnyx_cfg, True),
    ):
        line = get_yallasay_line_config(_FakeDb())

    assert line["whatsapp_messaging_profile_id"] == VALID_UUID
    assert line["messaging_profile_id"] == VALID_UUID


def test_resolve_inbound_wa_to_from_yallasay_profile():
    telnyx_cfg = {
        "sms_from_2": YALLASAY_PHONE,
        "whatsapp_from_2": YALLASAY_PHONE,
        "whatsapp_from": "+447822002055",
        "sms_messaging_profile_id_2": VALID_UUID,
        "whatsapp_messaging_profile_id_2": VALID_UUID,
        "whatsapp_messaging_profile_id": "50019e47-a9de-45bb-8e93-9e1abb3521cc",
    }

    class _FakeDb:
        pass

    record = {"messaging_profile_id": VALID_UUID, "direction": "inbound", "type": "WHATSAPP"}

    with patch(
        "app.services.yallasay_telnyx_line.ProviderSettingsService.get_platform_config_decrypted",
        return_value=(telnyx_cfg, True),
    ):
        from app.services.yallasay_telnyx_line import resolve_inbound_wa_to_e164

        assert resolve_inbound_wa_to_e164(_FakeDb(), record) == YALLASAY_PHONE


def test_resolve_inbound_wa_to_returns_none_without_profile():
    telnyx_cfg = {
        "sms_from_2": YALLASAY_PHONE,
        "whatsapp_messaging_profile_id_2": VALID_UUID,
    }

    class _FakeDb:
        pass

    with patch(
        "app.services.yallasay_telnyx_line.ProviderSettingsService.get_platform_config_decrypted",
        return_value=(telnyx_cfg, True),
    ):
        from app.services.yallasay_telnyx_line import resolve_inbound_wa_to_e164

        assert resolve_inbound_wa_to_e164(_FakeDb(), {"type": "WHATSAPP"}) is None
