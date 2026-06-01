"""Outbound voice allow-list by country (GB, AU, CA, USA) for Telnyx AI calls."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.services.messaging_log_service import normalize_e164
from app.services.telnyx_api_key import normalize_telnyx_e164

DEFAULT_PHONE_ALLOWLIST: dict[str, Any] = {
    "GB": {
        "code": "44",
        "landline_prefixes": ["1", "2", "3", "4", "5", "8", "9"],
        "landline_price": 0.0061,
        "mobile_prefixes": ["7", "71", "72", "73", "74", "75", "76", "77", "78", "79"],
        "mobile_price": 0.0092,
    },
    "AU": {
        "code": "61",
        "landline_prefixes": ["2", "3", "7", "8"],
        "landline_price": 0.0134,
        "mobile_prefixes": ["4", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49"],
        "mobile_price": 0.0362,
    },
    "CA": {
        "code": "1",
        "area_codes": [
            204, 226, 236, 249, 250, 289, 306, 343, 365, 367, 368, 369, 387, 403, 416, 418, 428, 431,
            437, 438, 450, 506, 514, 519, 548, 579, 581, 584, 587, 604, 613, 639, 647, 672, 683, 705,
            709, 742, 753, 778, 780, 782, 807, 819, 825, 867, 873, 902, 905, 942,
        ],
        "landline_price": 0.0050,
        "mobile_price": 0.0090,
    },
    "USA": {
        "code": "1",
        "default_price": 0.0070,
        "note": "All +1 numbers not matching Canada area codes",
    },
}

DEFAULT_PHONE_ALLOWLIST_ENABLED: dict[str, bool] = {
    "GB": True,
    "AU": True,
    "CA": True,
    "USA": True,
}


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _prefix_match(national: str, prefixes: list[str]) -> bool:
    clean = str(national or "").strip()
    if not clean:
        return False
    ordered = sorted({str(p).strip() for p in prefixes if str(p).strip()}, key=len, reverse=True)
    return any(clean.startswith(p) for p in ordered)


def _merge_allowlist(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = deepcopy(DEFAULT_PHONE_ALLOWLIST)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in base and isinstance(value, dict):
                base[key] = {**base[key], **value}
    return base


def _merge_enabled(raw: dict[str, Any] | None) -> dict[str, bool]:
    out = dict(DEFAULT_PHONE_ALLOWLIST_ENABLED)
    if isinstance(raw, dict):
        for key in out:
            if key in raw:
                out[key] = bool(raw[key])
    return out


class TelnyxPhoneAllowlistService:
    @staticmethod
    def load_from_telnyx_config(cfg: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, bool]]:
        cfg = cfg or {}
        return _merge_allowlist(cfg.get("phone_allowlist")), _merge_enabled(cfg.get("phone_allowlist_enabled"))

    @staticmethod
    def load(db: Session) -> tuple[dict[str, Any], dict[str, bool]]:
        from app.services.provider_settings import ProviderSettingsService

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        return TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg or {})

    @staticmethod
    def normalize_e164(raw: str) -> str:
        try:
            return normalize_telnyx_e164(str(raw or "").strip())
        except Exception:
            try:
                return normalize_e164(str(raw or "").strip())
            except Exception:
                return str(raw or "").strip()

    @staticmethod
    def _classify_nanp(national_10: str, allowlist: dict[str, Any]) -> str:
        digits = _digits(national_10)
        if len(digits) != 10:
            return "USA"
        area = int(digits[:3])
        ca_cfg = allowlist.get("CA") if isinstance(allowlist.get("CA"), dict) else {}
        area_codes = ca_cfg.get("area_codes") if isinstance(ca_cfg.get("area_codes"), list) else []
        ca_set = {int(x) for x in area_codes if str(x).isdigit()}
        return "CA" if area in ca_set else "USA"

    @staticmethod
    def _detect_country(e164: str, allowlist: dict[str, Any]) -> tuple[str | None, str]:
        digits = _digits(e164)
        if not digits:
            return None, ""
        if digits.startswith("44"):
            return "GB", digits[2:]
        if digits.startswith("61"):
            return "AU", digits[2:]
        if digits.startswith("1") and len(digits) >= 11:
            national = digits[1:]
            country = TelnyxPhoneAllowlistService._classify_nanp(national[:10], allowlist)
            return country, national[:10]
        return None, digits

    @staticmethod
    def validate_phone(
        phone: str,
        *,
        allowlist: dict[str, Any] | None = None,
        enabled: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        raw = str(phone or "").strip()
        if not raw:
            return {
                "allowed": False,
                "reason": "Phone number is required",
                "country": None,
                "line_type": None,
                "normalized": "",
            }

        try:
            normalized = TelnyxPhoneAllowlistService.normalize_e164(raw)
        except Exception:
            normalized = raw

        merged = _merge_allowlist(allowlist)
        flags = _merge_enabled(enabled)

        if not any(flags.values()):
            return {
                "allowed": False,
                "reason": "No calling regions are enabled — configure Admin → Integrations → Telnyx → Whitelist",
                "country": None,
                "line_type": None,
                "normalized": normalized,
            }

        country, national = TelnyxPhoneAllowlistService._detect_country(normalized, merged)
        if not country:
            return {
                "allowed": False,
                "reason": "Only GB, AU, CA, and US numbers can be called",
                "country": None,
                "line_type": None,
                "normalized": normalized,
            }

        if not flags.get(country, False):
            return {
                "allowed": False,
                "reason": f"{country} calling is disabled",
                "country": country,
                "line_type": None,
                "normalized": normalized,
            }

        cfg = merged.get(country) if isinstance(merged.get(country), dict) else {}

        if country in {"GB", "AU"}:
            mobile_prefixes = cfg.get("mobile_prefixes") if isinstance(cfg.get("mobile_prefixes"), list) else []
            landline_prefixes = cfg.get("landline_prefixes") if isinstance(cfg.get("landline_prefixes"), list) else []
            if _prefix_match(national, mobile_prefixes):
                return {
                    "allowed": True,
                    "reason": None,
                    "country": country,
                    "line_type": "mobile",
                    "normalized": normalized,
                    "price": cfg.get("mobile_price"),
                }
            if _prefix_match(national, landline_prefixes):
                return {
                    "allowed": True,
                    "reason": None,
                    "country": country,
                    "line_type": "landline",
                    "normalized": normalized,
                    "price": cfg.get("landline_price"),
                }
            return {
                "allowed": False,
                "reason": f"Can't call this number — not on the {country} allow list",
                "country": country,
                "line_type": None,
                "normalized": normalized,
            }

        if country == "CA":
            return {
                "allowed": True,
                "reason": None,
                "country": "CA",
                "line_type": "nanp",
                "normalized": normalized,
                "price": cfg.get("mobile_price") or cfg.get("landline_price"),
            }

        if country == "USA":
            return {
                "allowed": True,
                "reason": None,
                "country": "USA",
                "line_type": "nanp",
                "normalized": normalized,
                "price": cfg.get("default_price"),
            }

        return {
            "allowed": False,
            "reason": "Can't call this number",
            "country": country,
            "line_type": None,
            "normalized": normalized,
        }

    @staticmethod
    def validate_phone_db(db: Session, phone: str) -> dict[str, Any]:
        allowlist, enabled = TelnyxPhoneAllowlistService.load(db)
        return TelnyxPhoneAllowlistService.validate_phone(phone, allowlist=allowlist, enabled=enabled)

    @staticmethod
    def admin_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
        allowlist, enabled = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg or {})
        return {
            "phone_allowlist": allowlist,
            "phone_allowlist_enabled": enabled,
            "defaults": DEFAULT_PHONE_ALLOWLIST,
        }

    @staticmethod
    def parse_allowlist_json(raw: str) -> dict[str, Any]:
        parsed = json.loads(raw or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Allow list must be a JSON object")
        return _merge_allowlist(parsed)
