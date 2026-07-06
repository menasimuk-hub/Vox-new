from __future__ import annotations

import json
from typing import Any

from app.core.encryption import get_encryptor
from app.models.connection_profile import ConnectionProfile, PROVIDER_META, PROVIDER_TELNYX


def decrypt_profile_secret(token: str | None) -> str | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    try:
        return get_encryptor().decrypt_str(raw)
    except ValueError:
        return None


def telnyx_config_from_profile(profile: ConnectionProfile) -> dict[str, Any]:
    return {
        "api_key": decrypt_profile_secret(profile.telnyx_api_key_encrypted) or "",
        "whatsapp_from": str(profile.telnyx_number or "").strip(),
        "whatsapp_number": str(profile.telnyx_number or "").strip(),
        "whatsapp_messaging_profile_id": str(profile.telnyx_messaging_profile_id or "").strip(),
        "connection_id": str(profile.telnyx_connection_id or "").strip(),
        "outbound_voice_profile_id": str(profile.telnyx_outbound_voice_profile_id or "").strip(),
    }


def meta_config_from_profile(profile: ConnectionProfile) -> dict[str, Any]:
    return {
        "waba_id": str(profile.meta_waba_id or "").strip(),
        "phone_number_id": str(profile.meta_phone_number_id or "").strip(),
        "business_id": str(profile.meta_business_id or "").strip(),
        "access_token": decrypt_profile_secret(profile.meta_access_token_encrypted) or "",
        "app_secret": decrypt_profile_secret(profile.meta_app_secret_encrypted) or "",
        "webhook_verify_token": decrypt_profile_secret(profile.meta_webhook_verify_token_encrypted) or "",
        "whatsapp_from": str(profile.meta_whatsapp_from or "").strip(),
    }


def calling_config_from_profile(profile: ConnectionProfile) -> dict[str, Any]:
    regions: list[str] = []
    raw = str(profile.regions_json or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                regions = [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            regions = [part.strip() for part in raw.split(",") if part.strip()]
    return {
        "api_key": decrypt_profile_secret(profile.telnyx_api_key_encrypted) or "",
        "calling_number": str(profile.calling_number or "").strip(),
        "connection_id": str(profile.telnyx_connection_id or "").strip(),
        "outbound_voice_profile_id": str(profile.telnyx_outbound_voice_profile_id or "").strip(),
        "regions": regions,
        "label": str(profile.label or "").strip(),
    }


def provider_label(profile: ConnectionProfile) -> str:
    if profile.provider == PROVIDER_META:
        return "meta"
    if profile.provider == PROVIDER_TELNYX:
        return "telnyx"
    return str(profile.provider or "unknown")
