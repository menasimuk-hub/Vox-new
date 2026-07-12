"""WhatsApp destination policy (allow-all + blocklist) and Telnyx profile sync.

WhatsApp: all countries allowed unless ISO is in messaging_blocked_destinations.
SMS Telnyx profiles: whitelisted_destinations derived from the call allowlist.
WhatsApp Telnyx profiles: always sync ["*"] (blocks enforced in-app).
"""

from __future__ import annotations

import re
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

# Legacy default whitelist (kept for sanitize/backward-compatible config shape only).
DEFAULT_MESSAGING_DESTINATIONS_ENABLED: dict[str, bool] = {
    "GB": True,
    "US": True,
    "AU": True,
    "CA": True,
    "PS": True,
}

_WA_PROFILE_KEYS = (
    "whatsapp_messaging_profile_id",
    "whatsapp_messaging_profile_id_2",
)
_SMS_PROFILE_KEYS = (
    "messaging_profile_id",
    "sms_messaging_profile_id_2",
)


def _normalize_iso(raw: str) -> str | None:
    code = str(raw or "").strip().upper()
    if code == "USA":
        return "US"
    if code == "*":
        return "*"
    if len(code) == 2 and code.isalpha():
        return code
    return None


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", str(raw or ""))


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


def _merge_blocked(raw: Any) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            iso = _normalize_iso(str(key))
            if iso and iso != "*" and bool(value):
                out[iso] = True
    elif isinstance(raw, list):
        for item in raw:
            iso = _normalize_iso(str(item))
            if iso and iso != "*":
                out[iso] = True
    return out


class TelnyxMessagingDestinationsService:
    @staticmethod
    def load_from_telnyx_config(cfg: dict[str, Any] | None) -> tuple[dict[str, bool], bool, dict[str, bool]]:
        cfg = cfg or {}
        # WA is allow-all by default; missing key means True. Sanitize always persists True.
        allow_all = bool(cfg.get("messaging_allow_all_destinations", True))
        blocked = _merge_blocked(cfg.get("messaging_blocked_destinations"))
        return _merge_destinations(cfg.get("messaging_whitelisted_destinations")), allow_all, blocked

    @staticmethod
    def load(db: Session) -> tuple[dict[str, bool], bool, dict[str, bool]]:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        return TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg if isinstance(cfg, dict) else {})

    @staticmethod
    def to_telnyx_api_list(destinations: dict[str, bool], *, allow_all: bool) -> list[str]:
        if allow_all:
            return ["*"]
        enabled = sorted(iso for iso, on in destinations.items() if on and iso != "*")
        return enabled or ["*"]

    @staticmethod
    def whatsapp_telnyx_payload() -> list[str]:
        return ["*"]

    @staticmethod
    def sms_destinations_from_call_allowlist(cfg: dict[str, Any] | None) -> list[str]:
        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        _allowlist, enabled, _extras, extra_enabled, _removed = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg)
        isos: set[str] = set()
        for key, on in (enabled or {}).items():
            if not on:
                continue
            iso = _normalize_iso(str(key))
            if iso and iso != "*":
                isos.add(iso)
        for key, on in (extra_enabled or {}).items():
            if not on:
                continue
            iso = _normalize_iso(str(key))
            if iso and iso != "*":
                isos.add(iso)
        ordered = sorted(isos)
        return ordered or ["GB"]

    @staticmethod
    def _dial_map(extra_dial: dict[str, str] | None = None) -> list[tuple[str, str]]:
        """Return (dial, iso) pairs sorted longest dial first. Skip US/CA (+1) — handled via NANP."""
        pairs: dict[str, str] = {}
        for iso, meta in COUNTRY_META.items():
            if iso in {"US", "CA"}:
                continue
            dial = str(meta.get("dial") or "").strip()
            if dial:
                pairs[dial] = iso
        for iso, dial in (extra_dial or {}).items():
            code = _normalize_iso(str(iso))
            d = str(dial or "").strip()
            if code and code not in {"US", "CA", "*"} and d:
                pairs[d] = code
        return sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True)

    @staticmethod
    def detect_country_iso(phone: str, *, extra_dial: dict[str, str] | None = None) -> str | None:
        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        digits = _digits(phone)
        if not digits:
            return None
        if digits.startswith("1") and len(digits) >= 11:
            allowlist, _, extras, extra_enabled, _removed = TelnyxPhoneAllowlistService.load_from_telnyx_config({})
            country, _ = TelnyxPhoneAllowlistService._detect_country(
                f"+{digits}",
                allowlist,
                extras=extras,
                extra_enabled={**{k: False for k in extras}, **(extra_enabled or {})},
            )
            if country == "USA":
                return "US"
            if country == "CA":
                return "CA"
            return "US"
        for dial, iso in TelnyxMessagingDestinationsService._dial_map(extra_dial):
            if digits.startswith(dial):
                return iso
        return None

    @staticmethod
    def _extra_dial_from_config(cfg: dict[str, Any] | None) -> dict[str, str]:
        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        _allowlist, _enabled, extras, _extra_enabled, _removed = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg)
        out: dict[str, str] = {}
        for iso, row in (extras or {}).items():
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            norm = _normalize_iso(str(iso))
            if norm and code:
                out[norm] = code
        blocked_meta = cfg.get("messaging_blocked_dial") if isinstance(cfg, dict) else None
        if isinstance(blocked_meta, dict):
            for iso, dial in blocked_meta.items():
                norm = _normalize_iso(str(iso))
                d = str(dial or "").strip()
                if norm and d:
                    out[norm] = d
        return out

    @staticmethod
    def check_whatsapp_destination(
        phone: str,
        *,
        cfg: dict[str, Any] | None = None,
        blocked: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        _destinations, _allow_all, blocked_map = TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg)
        if blocked is not None:
            blocked_map = _merge_blocked(blocked)
        extra_dial = TelnyxMessagingDestinationsService._extra_dial_from_config(cfg)
        # Ensure blocked ISOs in COUNTRY_META / extra dial are detectable
        for iso in blocked_map:
            if iso in COUNTRY_META and COUNTRY_META[iso].get("dial"):
                extra_dial.setdefault(iso, str(COUNTRY_META[iso]["dial"]))
        country = TelnyxMessagingDestinationsService.detect_country_iso(phone, extra_dial=extra_dial)
        if country and blocked_map.get(country):
            return {
                "allowed": False,
                "country": country,
                "reason": f"WhatsApp to {country} is blocked — remove it from Admin → Telnyx → WhatsApp block list",
            }
        return {"allowed": True, "country": country, "reason": None}

    @staticmethod
    def check_whatsapp_destination_db(db: Session, phone: str) -> dict[str, Any]:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        return TelnyxMessagingDestinationsService.check_whatsapp_destination(
            phone,
            cfg=cfg if isinstance(cfg, dict) else {},
        )

    @staticmethod
    def admin_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
        destinations, _allow_all, blocked = TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg)
        blocked_rows = []
        for iso in sorted(blocked):
            meta = COUNTRY_META.get(iso, {})
            blocked_rows.append(
                {
                    "iso": iso,
                    "name": meta.get("name") or iso,
                    "dial": meta.get("dial") or "",
                    "blocked": True,
                }
            )
        return {
            "messaging_whitelisted_destinations": destinations,
            "messaging_allow_all_destinations": True,
            "messaging_blocked_destinations": blocked,
            "country_meta": deepcopy(COUNTRY_META),
            "blocked_rows": blocked_rows,
            "rows": blocked_rows,
            "whatsapp_telnyx_payload": TelnyxMessagingDestinationsService.whatsapp_telnyx_payload(),
            "sms_telnyx_payload": TelnyxMessagingDestinationsService.sms_destinations_from_call_allowlist(cfg),
            "telnyx_payload": TelnyxMessagingDestinationsService.whatsapp_telnyx_payload(),
        }

    @staticmethod
    def sanitize_config(cfg: dict[str, Any]) -> dict[str, Any]:
        out = dict(cfg)
        destinations, _allow_all, blocked = TelnyxMessagingDestinationsService.load_from_telnyx_config(cfg)
        out["messaging_whitelisted_destinations"] = destinations
        out["messaging_allow_all_destinations"] = True
        out["messaging_blocked_destinations"] = blocked
        return out

    @staticmethod
    def collect_profile_ids(config: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for key in (*_WA_PROFILE_KEYS, *_SMS_PROFILE_KEYS):
            value = str(config.get(key) or "").strip()
            if value and ProviderSettingsService.is_valid_messaging_profile_uuid(value) and value not in ids:
                ids.append(value)
        return ids

    @staticmethod
    def collect_profiles_by_channel(config: dict[str, Any]) -> tuple[list[str], list[str]]:
        wa_ids: list[str] = []
        sms_ids: list[str] = []
        for key in _WA_PROFILE_KEYS:
            value = str(config.get(key) or "").strip()
            if value and ProviderSettingsService.is_valid_messaging_profile_uuid(value) and value not in wa_ids:
                wa_ids.append(value)
        for key in _SMS_PROFILE_KEYS:
            value = str(config.get(key) or "").strip()
            if (
                value
                and ProviderSettingsService.is_valid_messaging_profile_uuid(value)
                and value not in wa_ids
                and value not in sms_ids
            ):
                sms_ids.append(value)
        return wa_ids, sms_ids

    @staticmethod
    def _patch_profile(
        client: httpx.Client,
        *,
        profile_id: str,
        payload_list: list[str],
        channel: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            resp = client.patch(
                f"https://api.telnyx.com/v2/messaging_profiles/{profile_id}",
                json={"whitelisted_destinations": payload_list},
            )
            resp.raise_for_status()
            data = resp.json().get("data") if resp.headers.get("content-type", "").startswith("application/json") else {}
            return (
                {
                    "profile_id": profile_id,
                    "channel": channel,
                    "whitelisted_destinations": (data or {}).get("whitelisted_destinations") or payload_list,
                },
                None,
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            return None, f"{profile_id}: HTTP {exc.response.status_code if exc.response else '?'} — {detail}"
        except Exception as exc:
            return None, f"{profile_id}: {exc}"

    @staticmethod
    def sync_to_telnyx_profiles(db: Session, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        if not enabled:
            return {"ok": False, "error": "Telnyx integration is disabled"}
        merged = ProviderSettingsService._validate_telnyx_config(cfg if isinstance(cfg, dict) else {})
        if isinstance(config, dict):
            merged = {**merged, **TelnyxMessagingDestinationsService.sanitize_config(config)}

        wa_ids, sms_ids = TelnyxMessagingDestinationsService.collect_profiles_by_channel(merged)
        if not wa_ids and not sms_ids:
            return {"ok": False, "error": "No messaging profile IDs configured — set profiles on Telnyx API tab first."}

        wa_payload = TelnyxMessagingDestinationsService.whatsapp_telnyx_payload()
        sms_payload = TelnyxMessagingDestinationsService.sms_destinations_from_call_allowlist(merged)

        try:
            api_key, _source = require_telnyx_api_key(db, merged)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        updated: list[dict[str, Any]] = []
        errors: list[str] = []

        with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), headers=headers) as client:
            for profile_id in wa_ids:
                row, err = TelnyxMessagingDestinationsService._patch_profile(
                    client, profile_id=profile_id, payload_list=wa_payload, channel="whatsapp"
                )
                if row:
                    updated.append(row)
                if err:
                    errors.append(err)
            for profile_id in sms_ids:
                row, err = TelnyxMessagingDestinationsService._patch_profile(
                    client, profile_id=profile_id, payload_list=sms_payload, channel="sms"
                )
                if row:
                    updated.append(row)
                if err:
                    errors.append(err)

        return {
            "ok": bool(updated),
            "partial": bool(updated and errors),
            "whatsapp_whitelisted_destinations": wa_payload,
            "sms_whitelisted_destinations": sms_payload,
            "whitelisted_destinations": wa_payload,
            "profiles_updated": updated,
            "errors": errors,
            "message": (
                f"Updated {len(updated)} profile(s): WA={wa_payload}, SMS={sms_payload}"
                if updated and not errors
                else (
                    f"Updated {len(updated)} profile(s); {len(errors)} failed"
                    if updated
                    else "No profiles updated"
                )
            ),
        }
