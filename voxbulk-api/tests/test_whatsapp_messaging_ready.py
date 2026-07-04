"""Survey dispatch readiness when Meta WhatsApp is primary."""

from __future__ import annotations

from app.services.whatsapp_provider_service import whatsapp_messaging_ready


def test_whatsapp_messaging_ready_meta_primary_without_telnyx(monkeypatch):
    monkeypatch.setattr(
        "app.services.whatsapp_provider_service.is_meta_whatsapp_primary",
        lambda _db: True,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_provider_service.ProviderSettingsService.get_platform_config_decrypted",
        lambda _db, provider: (
            {
                "access_token": "token",
                "phone_number_id": "1183491521519203",
                "waba_id": "1033532842963987",
            },
            True,
        ),
    )
    monkeypatch.setattr(
        "app.services.telnyx_messaging_service.TelnyxMessagingService.is_configured",
        lambda _db: {"enabled": False, "sms": False, "whatsapp": False},
    )

    ready = whatsapp_messaging_ready(None)
    assert ready["enabled"] is True
    assert ready["whatsapp"] is True
    assert ready["provider"] == "meta_whatsapp"
    assert ready["meta_whatsapp"] is True
