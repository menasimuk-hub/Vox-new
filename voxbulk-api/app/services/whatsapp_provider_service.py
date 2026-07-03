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
