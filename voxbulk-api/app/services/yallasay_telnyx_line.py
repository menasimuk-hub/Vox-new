"""Yallasay dedicated Telnyx line (Number 2) — Abuu WhatsApp only.

Number 1 (whatsapp_from): surveys + AI calling — never Abuu.
Number 2 (sms_from_2 / whatsapp_from_2): Abuu / YallaSay ordering only.
Both numbers can receive inbound WhatsApp; routing uses is_yallasay_line(to).
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.messaging_log_service import normalize_e164
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import require_telnyx_api_key

logger = logging.getLogger(__name__)

YALLASAY_PROFILE_NAME = "voxbulk-yallasay"


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
    sms_profile = str(config.get("sms_messaging_profile_id_2") or "").strip() or None
    wa_profile = (
        str(config.get("whatsapp_messaging_profile_id_2") or config.get("sms_messaging_profile_id_2") or "").strip()
        or None
    )
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


def persist_yallasay_profile_ids(db: Session, profile_id: str, *, phone: str | None = None) -> None:
    """Write Yallasay messaging profile UUIDs into platform Telnyx config."""
    pid = ProviderSettingsService.sanitize_messaging_profile_id(
        str(profile_id or "").strip(),
        field="sms_messaging_profile_id_2",
    )
    if not pid:
        return
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    row = ProviderSettingsService.get_platform_config(db, provider="telnyx")
    merged = dict(cfg if isinstance(cfg, dict) else {})
    merged["sms_messaging_profile_id_2"] = pid
    merged["whatsapp_messaging_profile_id_2"] = pid
    if phone:
        norm = _norm(phone)
        if norm:
            merged["sms_from_2"] = norm
            merged["whatsapp_from_2"] = norm
    ProviderSettingsService.upsert_platform_config(
        db,
        provider="telnyx",
        is_enabled=bool(row.is_enabled if row else enabled),
        config=merged,
    )
    db.commit()


def _telnyx_api_headers(db: Session) -> tuple[str, dict[str, str]] | None:
    config = _telnyx_config(db)
    try:
        api_key, _source = require_telnyx_api_key(db, config)
    except ValueError:
        return None
    return api_key, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def fetch_voxbulk_yallasay_profile_id_from_telnyx(db: Session) -> str | None:
    auth = _telnyx_api_headers(db)
    if not auth:
        return None
    _api_key, headers = auth
    try:
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify(), headers=headers) as client:
            resp = client.get("https://api.telnyx.com/v2/messaging_profiles", params={"page[size]": 100})
            resp.raise_for_status()
            for row in resp.json().get("data") or []:
                if isinstance(row, dict) and str(row.get("name") or "").strip().lower() == YALLASAY_PROFILE_NAME:
                    pid = ProviderSettingsService.sanitize_messaging_profile_id(
                        str(row.get("id") or "").strip(),
                        field="sms_messaging_profile_id_2",
                    )
                    if pid:
                        return pid
    except Exception as exc:
        logger.warning("yallasay_fetch_profile_by_name failed err=%s", exc)
    return None


def fetch_messaging_profile_id_for_phone_from_telnyx(db: Session, phone: str) -> str | None:
    norm = _norm(phone)
    if not norm:
        return None
    auth = _telnyx_api_headers(db)
    if not auth:
        return None
    _api_key, headers = auth
    try:
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify(), headers=headers) as client:
            resp = client.get(f"https://api.telnyx.com/v2/messaging_phone_numbers/{quote(norm, safe='')}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            if not isinstance(data, dict):
                return None
            pid = ProviderSettingsService.sanitize_messaging_profile_id(
                str(data.get("messaging_profile_id") or "").strip(),
                field="sms_messaging_profile_id_2",
            )
            return pid or None
    except Exception as exc:
        logger.warning("yallasay_fetch_profile_for_phone failed phone=%s err=%s", norm, exc)
    return None


def resolve_yallasay_whatsapp_messaging_profile_id(db: Session, *, persist: bool = False) -> str | None:
    """Config UUID first, then Telnyx lookup (voxbulk-yallasay profile or number assignment)."""
    line = get_yallasay_line_config(db)
    profile = str(line.get("whatsapp_messaging_profile_id") or "").strip()
    if profile:
        return profile

    fetched = fetch_voxbulk_yallasay_profile_id_from_telnyx(db)
    if not fetched:
        phone = line.get("whatsapp_phone") or line.get("phone")
        if phone:
            fetched = fetch_messaging_profile_id_for_phone_from_telnyx(db, phone)

    if fetched and persist:
        persist_yallasay_profile_ids(db, fetched)
        logger.info("yallasay_profile_persisted source=telnyx_lookup profile=%s", fetched)
    return fetched


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


def _extract_messaging_profile_id(record: dict[str, Any]) -> str:
    if not isinstance(record, dict):
        return ""
    direct = str(record.get("messaging_profile_id") or "").strip()
    if direct:
        return direct
    for nested_key in ("payload", "message", "data"):
        nested = record.get(nested_key)
        if isinstance(nested, dict):
            nested_id = str(nested.get("messaging_profile_id") or "").strip()
            if nested_id:
                return nested_id
    return ""


def resolve_inbound_wa_to_e164(
    db: Session,
    record: dict[str, Any],
    *,
    explicit_to: str | None = None,
) -> str | None:
    """Resolve inbound WhatsApp destination when Telnyx omits the `to` field.

    Uses messaging_profile_id only — never blind-defaults to Yallasay.
    """
    resolved = _norm(explicit_to) if explicit_to else None
    if resolved:
        return resolved

    profile_id = _extract_messaging_profile_id(record)
    if not profile_id:
        return None

    config = _telnyx_config(db)
    line = get_yallasay_line_config(db)
    yalla_profiles = {
        str(line.get("whatsapp_messaging_profile_id") or "").strip(),
        str(line.get("messaging_profile_id") or "").strip(),
    } - {""}
    survey_profile = str(
        config.get("whatsapp_messaging_profile_id") or config.get("messaging_profile_id") or ""
    ).strip()

    if profile_id in yalla_profiles:
        inferred = get_yallasay_whatsapp_e164(db)
        if inferred:
            logger.info(
                "yallasay_inbound_to_inferred source=messaging_profile_id to=%s profile=%s",
                inferred,
                profile_id,
            )
        return inferred

    if survey_profile and profile_id == survey_profile:
        return _norm(str(config.get("whatsapp_from") or ""))

    return None
