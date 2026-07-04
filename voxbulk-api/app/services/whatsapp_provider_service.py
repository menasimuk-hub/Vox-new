"""Route WhatsApp send/sync through Meta Cloud API when meta_whatsapp is enabled."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService


def is_meta_whatsapp_primary(db: Session) -> bool:
    """True when Meta WhatsApp is enabled and has credentials for production sends."""
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    if not enabled:
        return False
    try:
        config = validate_meta_whatsapp_config(cfg or {})
    except Exception:
        return False
    return bool(
        str(config.get("access_token") or "").strip()
        and str(config.get("phone_number_id") or "").strip()
        and str(config.get("waba_id") or "").strip()
    )


def meta_whatsapp_config(db: Session) -> tuple[dict[str, Any], bool]:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    return validate_meta_whatsapp_config(cfg or {}), bool(enabled)


def whatsapp_messaging_ready(db: Session) -> dict[str, Any]:
    """
    Whether outbound WhatsApp (and SMS fallback) can be sent for survey/campaign dispatch.

    When Meta WhatsApp is primary, WhatsApp readiness follows Meta credentials — not Telnyx.
    Telnyx is still checked for SMS-only paths and legacy fallback.
    """
    from app.services.telnyx_messaging_service import TelnyxMessagingService

    telnyx = TelnyxMessagingService.is_configured(db)
    if is_meta_whatsapp_primary(db):
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        config = validate_meta_whatsapp_config(cfg or {})
        meta_whatsapp = bool(
            enabled
            and str(config.get("access_token") or "").strip()
            and str(config.get("phone_number_id") or "").strip()
            and str(config.get("waba_id") or "").strip()
        )
        provider = "meta_whatsapp" if meta_whatsapp else ("telnyx" if telnyx.get("whatsapp") else None)
        return {
            "enabled": meta_whatsapp or bool(telnyx.get("enabled")),
            "whatsapp": meta_whatsapp or bool(telnyx.get("whatsapp")),
            "sms": bool(telnyx.get("sms")),
            "provider": provider,
            "meta_whatsapp": meta_whatsapp,
            "telnyx": telnyx,
        }
    return {
        **telnyx,
        "provider": "telnyx" if telnyx.get("enabled") else None,
        "meta_whatsapp": False,
        "telnyx": telnyx,
    }
