"""Yallasay dedicated Telnyx line (Admin → Integrations → Telnyx → SMS number 2)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.messaging_log_service import normalize_e164
from app.services.provider_settings import ProviderSettingsService


def get_yallasay_line_e164(db: Session) -> str | None:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not isinstance(cfg, dict):
        return None
    config = ProviderSettingsService._validate_telnyx_config(cfg)
    raw = str(config.get("sms_from_2") or config.get("yallasay_from") or "").strip()
    if not raw:
        return None
    try:
        return normalize_e164(raw)
    except ValueError:
        return raw or None


def is_yallasay_line(db: Session, phone: str | None) -> bool:
    line = get_yallasay_line_e164(db)
    if not line or not phone:
        return False
    try:
        return normalize_e164(phone) == line
    except ValueError:
        return str(phone or "").strip() == line
