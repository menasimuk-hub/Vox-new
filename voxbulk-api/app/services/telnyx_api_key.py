from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings


TELNYX_API_KEY_MIN_LENGTH = 50


def normalize_telnyx_api_key(raw: str) -> str:
    key = str(raw or "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {'"', "'"}:
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    # Strip only whitespace/newlines — do not remove characters inside the key.
    key = key.replace("\r", "").replace("\n", "").replace("\t", "")
    return key.strip()


def _telnyx_integrations_config(db: Session) -> dict[str, Any]:
    """Load decrypted Telnyx settings saved under admin → Integrations."""
    from app.services.provider_settings import ProviderSettingsService

    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not cfg:
        return {}
    return ProviderSettingsService._validate_telnyx_config(cfg)


def resolve_telnyx_api_key(db: Session | None, config: dict[str, Any] | None = None) -> tuple[str, str]:
    cfg = dict(config or {})
    inline_key = normalize_telnyx_api_key(str(cfg.get("api_key") or ""))
    if inline_key:
        return inline_key, "inline_config"
    if db is not None:
        platform_cfg = _telnyx_integrations_config(db)
        platform_key = normalize_telnyx_api_key(str(platform_cfg.get("api_key") or ""))
        if platform_key:
            return platform_key, "platform_integrations"
    env_key = normalize_telnyx_api_key(str(get_settings().telnyx_api_key or os.getenv("TELNYX_API_KEY") or ""))
    if env_key:
        return env_key, "TELNYX_API_KEY"
    return "", ""


def telnyx_key_fingerprint(api_key: str) -> dict[str, Any]:
    key = normalize_telnyx_api_key(api_key)
    if not key:
        return {"length": 0, "prefix": "", "looks_valid": False, "expected_length": 58}
    valid_prefix = key.startswith("KEY")
    valid_len = len(key) >= TELNYX_API_KEY_MIN_LENGTH
    return {
        "length": len(key),
        "prefix": key[:7] + "…" if len(key) > 7 else key,
        "looks_valid": valid_prefix and valid_len,
        "expected_length": 58,
        "too_short": bool(key) and valid_prefix and not valid_len,
    }


def telnyx_outbound_caller_id(config: dict[str, Any] | None) -> str:
    """Prefer explicit outbound fields over legacy fallback_caller_id."""
    cfg = config or {}
    return str(
        cfg.get("default_outbound_number") or cfg.get("from_phone_number") or cfg.get("fallback_caller_id") or ""
    ).strip()


def normalize_telnyx_e164(raw: str) -> str:
    """Normalize to E.164; UK local numbers starting with 0 become +44…"""
    from app.services.twilio_service import normalize_e164

    s = str(raw or "").strip().replace(" ", "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("0") and len(s) >= 10 and s[1:].isdigit():
        s = "+44" + s[1:]
    return normalize_e164(s)


def telnyx_caller_hint(from_number: str, account_numbers: list[str] | None = None) -> str:
    nums = account_numbers or []
    if len(nums) == 1 and from_number and from_number != nums[0]:
        return (
            f"From number is wrong: you have “{from_number}” saved but your Telnyx number is “{nums[0]}”. "
            f"Update From phone number to {nums[0]}, click Save Telnyx, then Test call again."
        )
    sample = ", ".join(nums[:5]) if nums else "(check Telnyx Portal → Numbers)"
    return (
        f"Telnyx rejected the caller ID “{from_number}”. "
        f"Set From phone number to a number you own in Telnyx (e.g. {sample}), "
        "in E.164 format (+44…), and assign it to the same Call Control application as your Connection ID."
    )


def telnyx_auth_hint(api_key: str) -> str:
    fp = telnyx_key_fingerprint(api_key)
    if not fp["length"]:
        return (
            "Telnyx API key not found. In admin → Integrations → Telnyx, paste your secret API key (starts with KEY), "
            "click Save Telnyx, then retry. Or set TELNYX_API_KEY in voxbulk-api/.env and restart the API."
        )
    if fp.get("too_short"):
        return (
            f"API key is only {fp['length']} characters; Telnyx secret keys are about {fp['expected_length']} characters. "
            "You copied a partial key. In Telnyx Portal → API Keys, create a new key and copy the entire value in one go."
        )
    if not fp["looks_valid"]:
        return (
            f"The stored value ({fp['prefix']}, length {fp['length']}) is not a Telnyx API key. "
            "In Telnyx Portal → API Keys, create/copy the full secret key that starts with KEY — "
            "not the Connection ID, not the phone number, not a webhook signing secret."
        )
    return (
        "Telnyx rejected this API key. Create a new key in Telnyx Portal → API Keys, "
        "paste it in the API key field (no Bearer prefix), click Save Telnyx, then test again."
    )


def require_telnyx_api_key(db: Session | None, config: dict[str, Any] | None = None) -> tuple[str, str]:
    """Resolve API key or raise ValueError with an actionable message (before calling Telnyx)."""
    api_key, source = resolve_telnyx_api_key(db, config)
    fp = telnyx_key_fingerprint(api_key)
    if not fp["length"]:
        raise ValueError(telnyx_auth_hint(""))
    if fp.get("too_short") or not fp["looks_valid"]:
        raise ValueError(telnyx_auth_hint(api_key))
    return api_key, source
