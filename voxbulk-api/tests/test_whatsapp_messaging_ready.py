"""Survey dispatch readiness when Meta WhatsApp is primary."""

from __future__ import annotations

from app.services.whatsapp_provider_service import whatsapp_messaging_ready


def test_whatsapp_messaging_ready_meta_primary_without_telnyx(monkeypatch):
    from unittest.mock import MagicMock

    from app.services.connection.config_resolver import WhatsappRouteConfig

    monkeypatch.setattr(
        "app.services.whatsapp_provider_service.resolve_whatsapp_config",
        lambda _db, **kwargs: WhatsappRouteConfig(
            profile=None,
            provider="meta",
            config={
                "access_token": "token",
                "phone_number_id": "1183491521519203",
                "waba_id": "1033532842963987",
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.telnyx_messaging_service.TelnyxMessagingService.is_configured",
        lambda _db: {"enabled": False, "sms": False, "whatsapp": False},
    )

    ready = whatsapp_messaging_ready(MagicMock())
    assert ready["enabled"] is True
    assert ready["whatsapp"] is True
    assert ready["provider"] == "meta_whatsapp"
    assert ready["meta_whatsapp"] is True
