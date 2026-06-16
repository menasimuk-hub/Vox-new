"""Yallasay dedicated Telnyx line (Number 2) — Abuu WhatsApp only.

Number 1 (whatsapp_from): surveys + AI calling — never Abuu.
Number 2 (sms_from_2 / whatsapp_from_2): Abuu / YallaSay ordering only.
Both numbers can receive inbound WhatsApp; routing uses is_yallasay_line(to).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.messaging_log_service import normalize_e164
from app.services.provider_settings import ProviderSettingsService


def _telnyx_config(db: Session) -> dict[str, Any]:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not isinstance(cfg, dict):
        return {}
    return ProviderSettingsService._validate_telnyx_config(cfg)


def _norm(phone: str | None) -> str | None:
    raw = str(phone or "").strip()
    if not raw:
        return None
    try:
        return normalize_e164(raw)
    except ValueError:
        return raw


def get_yallasay_line_e164(db: Session) -> str | None:
    config = _telnyx_config(db)
    return _norm(str(config.get("sms_from_2") or config.get("yallasay_from") or ""))


def get_yallasay_whatsapp_e164(db: Session) -> str | None:
    config = _telnyx_config(db)
    return _norm(
        str(config.get("whatsapp_from_2") or config.get("sms_from_2") or config.get("yallasay_from") or "")
    )


def get_yallasay_line_config(db: Session) -> dict[str, Any]:
    config = _telnyx_config(db)
    phone = get_yallasay_line_e164(db)
    wa_phone = get_yallasay_whatsapp_e164(db)
    sms_profile = str(
        config.get("sms_messaging_profile_id_2") or config.get("messaging_profile_id_2") or ""
    ).strip()
    wa_profile = str(
        config.get("whatsapp_messaging_profile_id_2")
        or config.get("sms_messaging_profile_id_2")
        or config.get("whatsapp_messaging_profile_id")
        or config.get("messaging_profile_id")
        or ""
    ).strip()
    base = str(config.get("webhook_base_url") or "").strip().rstrip("/")
    messaging_webhook_url = str(config.get("messaging_webhook_url") or "").strip()
    if not messaging_webhook_url and base:
        messaging_webhook_url = f"{base}/telnyx/webhooks/messages"
    return {
        "phone": phone,
        "whatsapp_phone": wa_phone,
        "messaging_profile_id": sms_profile or None,
        "whatsapp_messaging_profile_id": wa_profile or None,
        "messaging_webhook_url": messaging_webhook_url or None,
    }


def is_yallasay_line(db: Session, phone: str | None) -> bool:
    if not phone:
        return False
    target = _norm(phone)
    if not target:
        return False
    for candidate in (get_yallasay_line_e164(db), get_yallasay_whatsapp_e164(db)):
        if candidate and candidate == target:
            return True
    return False
