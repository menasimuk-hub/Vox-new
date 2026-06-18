"""Telnyx messaging profile whitelisted destinations (SMS + WhatsApp outbound)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import require_telnyx_api_key

# ISO 3166-1 alpha-2 → display metadata (extend in Admin with custom rows).
COUNTRY_META: dict[str, dict[str, str]] = {
    "GB": {"name": "United Kingdom", "dial": "44"},
    "US": {"name": "United States", "dial": "1"},
    "AU": {"name": "Australia", "dial": "61"},
    "CA": {"name": "Canada", "dial": "1"},
    "PS": {"name": "Palestine", "dial": "970"},
    "AE": {"name": "United Arab Emirates", "dial": "971"},
    "SA": {"name": "Saudi Arabia", "dial": "966"},
    "EG": {"name": "Egypt", "dial": "20"},
    "JO": {"name": "Jordan", "dial": "962"},
    "LB": {"name": "Lebanon", "dial": "961"},
    "IL": {"name": "Israel", "dial": "972"},
    "DE": {"name": "Germany", "dial": "49"},
    "FR": {"name": "France", "dial": "33"},
}

DEFAULT_MESSAGING_DESTINATIONS_ENABLED: dict[str, bool] = {
    "GB": True,
    "US": True,
    "AU": True,
    "CA": True,
    "PS": True,
}


def _normalize_iso(raw: str) -> str | None:
    code = str(raw or "").strip().upper()
    if code == "*":
        return "*"
    if len(code) == 2 and code.isalpha():
        return code
    return None


def _merge_destinations(raw: Any) -> dict[str, bool]:
    out = dict(DEFAULT_MESSAGING_DESTINATIONS_ENABLED)
    if isinstance(raw, dict):
        for key, value in raw.items():
            iso = _normalize_iso(str(key))
            if iso and iso != "*":
                out[iso] = bool(value)
    elif isinstance(raw, list):
        for item in raw:
            iso = _normalize_iso(str(item))
            if iso and iso != "*":
                out[iso] = True
    return out


class TelnyxMessagingDestinationsService:
    @staticmethod
    def load_from_telnyx_config(cfg: dict[str, Any] | None) -> tuple[dict[str, bool], bool]:
        cfg = cfg or {}
        allow_all = bool(cfg.get("messaging_allow_all_destinations"))
        return _merge_destinations(cfg.get("messaging_whitelisted_destinations")), allow_all

    @staticmethod
    def load(db: Session) -> tuple[dict[str, bool], bool]:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        return TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg if isinstance(cfg, dict) else {})

    @staticmethod
    def to_telnyx_api_list(destinations: dict[str, bool], *, allow_all: bool) -> list[str]:
        if allow_all:
            return ["*"]
        enabled = sorted(iso for iso, on in destinations.items() if on and iso != "*")
        return enabled or ["*"]

    @staticmethod
    def admin_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
        destinations, allow_all = TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg)
        rows = []
        for iso in sorted(set(destinations) | set(COUNTRY_META)):
            if iso == "*":
                continue
            meta = COUNTRY_META.get(iso, {})
            rows.append(
                {
                    "iso": iso,
                    "name": meta.get("name") or iso,
                    "dial": meta.get("dial") or "",
                    "enabled": bool(destinations.get(iso, False)),
                }
            )
        return {
            "messaging_whitelisted_destinations": destinations,
            "messaging_allow_all_destinations": allow_all,
            "country_meta": deepcopy(COUNTRY_META),
            "rows": rows,
            "telnyx_payload": TelnyxMessagingDestinationsService.to_telnyx_api_list(destinations, allow_all=allow_all),
        }

    @staticmethod
    def sanitize_config(cfg: dict[str, Any]) -> dict[str, Any]:
        out = dict(cfg)
        destinations, allow_all = TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg)
        out["messaging_whitelisted_destinations"] = destinations
        out["messaging_allow_all_destinations"] = allow_all
        return out

    @staticmethod
    def collect_profile_ids(config: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for key in (
            "messaging_profile_id",
            "whatsapp_messaging_profile_id",
            "sms_messaging_profile_id_2",
            "whatsapp_messaging_profile_id_2",
        ):
            value = str(config.get(key) or "").strip()
            if value and ProviderSettingsService.is_valid_messaging_profile_uuid(value) and value not in ids:
                ids.append(value)
        return ids

    @staticmethod
    def sync_to_telnyx_profiles(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        if not enabled:
            return {"ok": False, "error": "Telnyx integration is disabled"}
        merged = ProviderSettingsService._validate_telnyx_config(cfg if isinstance(cfg, dict) else {})
        if isinstance(config, dict):
            merged = {**merged, **TelnyxMessagingDestinationsService.sanitize_config(config)}

        profile_ids = TelnyxMessagingDestinationsService.collect_profile_ids(merged)
        if not profile_ids:
            return {"ok": False, "error": "No messaging profile IDs configured — set profiles on Telnyx API tab first."}

        destinations, allow_all = TelnyxMessagingDestinationsService.load_from_telnyx_config(merged)
        payload_list = TelnyxMessagingDestinationsService.to_telnyx_api_list(destinations, allow_all=allow_all)

        try:
            api_key, _source = require_telnyx_api_key(db, merged)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        updated: list[dict[str, Any]] = []
        errors: list[str] = []

        with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), headers=headers) as client:
            for profile_id in profile_ids:
                try:
                    resp = client.patch(
                        f"https://api.telnyx.com/v2/messaging_profiles/{profile_id}",
                        json={"whitelisted_destinations": payload_list},
                    )
                    resp.raise_for_status()
                    data = resp.json().get("data") if resp.headers.get("content-type", "").startswith("application/json") else {}
                    updated.append(
                        {
                            "profile_id": profile_id,
                            "whitelisted_destinations": (data or {}).get("whitelisted_destinations") or payload_list,
                        }
                    )
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text[:300] if exc.response is not None else str(exc)
                    errors.append(f"{profile_id}: HTTP {exc.response.status_code if exc.response else '?'} — {detail}")
                except Exception as exc:
                    errors.append(f"{profile_id}: {exc}")

        return {
            "ok": bool(updated),
            "partial": bool(updated and errors),
            "whitelisted_destinations": payload_list,
            "profiles_updated": updated,
            "errors": errors,
            "message": (
                f"Updated {len(updated)} messaging profile(s) with {payload_list}"
                if updated and not errors
                else (
                    f"Updated {len(updated)} profile(s); {len(errors)} failed"
                    if updated
                    else "No profiles updated"
                )
            ),
        }
