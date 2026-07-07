"""Route WhatsApp send/sync through connection profiles (Meta or Telnyx)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.connection.config_resolver import resolve_whatsapp_config, whatsapp_provider_is_meta
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService


def is_meta_whatsapp_primary(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = None,
    connection_profile_id: str | None = None,
) -> bool:
    """True when the resolved WhatsApp route uses Meta Cloud API."""
    return whatsapp_provider_is_meta(
        db,
        org_id=org_id,
        service_code=service_code,
        connection_profile_id=connection_profile_id,
    )


def meta_whatsapp_config(db: Session) -> tuple[dict[str, Any], bool]:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    return validate_meta_whatsapp_config(cfg or {}), bool(enabled)


def whatsapp_messaging_ready(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = None,
) -> dict[str, Any]:
    """
    Whether outbound WhatsApp can be sent for the resolved route (profile or platform fallback).
    """
    from app.services.telnyx_messaging_service import TelnyxMessagingService

    telnyx = (
        TelnyxMessagingService.is_configured(db)
        if db is not None
        else {"enabled": False, "sms": False, "whatsapp": False}
    )
    route = resolve_whatsapp_config(db, org_id=org_id, service_code=service_code) if db is not None else None
    if route is None:
        return {
            **telnyx,
            "provider": None,
            "meta_whatsapp": False,
            "telnyx": telnyx,
            "enabled": bool(telnyx.get("enabled")),
            "whatsapp": bool(telnyx.get("whatsapp")),
            "sms": bool(telnyx.get("sms")),
        }

    if route.is_meta:
        meta_ok = bool(
            str(route.config.get("access_token") or "").strip()
            and str(route.config.get("phone_number_id") or "").strip()
            and str(route.config.get("waba_id") or "").strip()
        )
        return {
            "enabled": meta_ok or bool(telnyx.get("enabled")),
            "whatsapp": meta_ok or bool(telnyx.get("whatsapp")),
            "sms": bool(telnyx.get("sms")),
            "provider": "meta_whatsapp" if meta_ok else ("telnyx" if telnyx.get("whatsapp") else None),
            "meta_whatsapp": meta_ok,
            "telnyx": telnyx,
            "connection_profile_id": route.profile.id if route.profile else None,
            "connection_profile_provider": route.provider,
        }

    telnyx_ok = bool(
        str(route.config.get("api_key") or "").strip()
        and str(route.config.get("whatsapp_from") or route.config.get("whatsapp_number") or "").strip()
    )
    return {
        "enabled": telnyx_ok or bool(telnyx.get("enabled")),
        "whatsapp": telnyx_ok or bool(telnyx.get("whatsapp")),
        "sms": bool(telnyx.get("sms")),
        "provider": "telnyx" if telnyx_ok else None,
        "meta_whatsapp": False,
        "telnyx": telnyx,
        "connection_profile_id": route.profile.id if route.profile else None,
        "connection_profile_provider": route.provider,
    }
