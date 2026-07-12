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

# Extra dial regions for AI voice calls (not used for WhatsApp/SMS).
DEFAULT_PHONE_ALLOWLIST_EXTRA: dict[str, Any] = {
    "PS": {
        "code": "970",
        "name": "Palestine",
        "allow_any_prefix": True,
    },
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


def _merge_extra(raw: Any, *, seed_defaults: bool) -> dict[str, Any]:
    # When the key is absent from config, seed DEFAULT extras (e.g. PS).
    # Once stored (even {}), the saved dict is the membership source of truth so deletes stick.
    if seed_defaults and not isinstance(raw, dict):
        return deepcopy(DEFAULT_PHONE_ALLOWLIST_EXTRA)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        iso = str(key or "").strip().upper()
        if not iso or not isinstance(value, dict):
            continue
        template = DEFAULT_PHONE_ALLOWLIST_EXTRA.get(iso, {})
        merged = {**template, **value} if isinstance(template, dict) else dict(value)
        if "code" in value:
            merged["code"] = str(value.get("code") or "").strip()
        if "name" in value:
            merged["name"] = str(value.get("name") or iso).strip()
        out[iso] = merged
    return out


def _merge_extra_enabled(raw: dict[str, Any] | None, extras: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    enabled_raw = raw if isinstance(raw, dict) else {}
    for iso in extras:
        if iso in enabled_raw:
            out[iso] = bool(enabled_raw[iso])
        else:
            out[iso] = False
    return out


def _merge_removed(raw: Any) -> list[str]:
    """Core regions (GB/AU/CA/USA) removed from the Admin call list."""
    core = set(DEFAULT_PHONE_ALLOWLIST_ENABLED)
    out: list[str] = []
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [k for k, v in raw.items() if v]
    else:
        items = []
    for item in items:
        iso = str(item or "").strip().upper()
        if iso == "US":
            iso = "USA"
        if iso in core and iso not in out:
            out.append(iso)
    return out


class TelnyxPhoneAllowlistService:
    @staticmethod
    def load_from_telnyx_config(
        cfg: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, bool], dict[str, Any], dict[str, bool], list[str]]:
        cfg = cfg or {}
        seed_extra = "phone_allowlist_extra" not in cfg
        extras = _merge_extra(cfg.get("phone_allowlist_extra"), seed_defaults=seed_extra)
        removed = _merge_removed(cfg.get("phone_allowlist_removed"))
        enabled = _merge_enabled(cfg.get("phone_allowlist_enabled"))
        for iso in removed:
            enabled[iso] = False
        return (
            _merge_allowlist(cfg.get("phone_allowlist")),
            enabled,
            extras,
            _merge_extra_enabled(cfg.get("phone_allowlist_extra_enabled"), extras),
            removed,
        )

    @staticmethod
    def load(db: Session) -> tuple[dict[str, Any], dict[str, bool], dict[str, Any], dict[str, bool], list[str]]:
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
    def _detect_extra_country(
        e164: str,
        extras: dict[str, Any],
        extra_enabled: dict[str, bool],
    ) -> tuple[str | None, str]:
        digits = _digits(e164)
        if not digits:
            return None, ""
        ordered = sorted(
            extras.items(),
            key=lambda item: len(str((item[1] or {}).get("code") or "")),
            reverse=True,
        )
        for iso, cfg in ordered:
            if not extra_enabled.get(iso, False):
                continue
            if not isinstance(cfg, dict):
                continue
            code = str(cfg.get("code") or "").strip()
            if code and digits.startswith(code):
                return iso, digits[len(code) :]
        return None, ""

    @staticmethod
    def _detect_country(
        e164: str,
        allowlist: dict[str, Any],
        *,
        extras: dict[str, Any] | None = None,
        extra_enabled: dict[str, bool] | None = None,
    ) -> tuple[str | None, str]:
        iso, national = TelnyxPhoneAllowlistService._detect_extra_country(
            e164,
            extras or {},
            extra_enabled or {},
        )
        if iso:
            return iso, national

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
        extras: dict[str, Any] | None = None,
        extra_enabled: dict[str, bool] | None = None,
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
        merged_extras = _merge_extra(extras)
        merged_extra_flags = _merge_extra_enabled(extra_enabled, merged_extras)

        if not any(flags.values()) and not any(merged_extra_flags.values()):
            return {
                "allowed": False,
                "reason": "No calling regions are enabled — configure Admin → Integrations → Telnyx → Call allowlist",
                "country": None,
                "line_type": None,
                "normalized": normalized,
            }

        country, national = TelnyxPhoneAllowlistService._detect_country(
            normalized,
            merged,
            extras=merged_extras,
            extra_enabled=merged_extra_flags,
        )
        if not country:
            return {
                "allowed": False,
                "reason": "Number country is not on the call allowlist — add the region in Admin → Telnyx → Call allowlist",
                "country": None,
                "line_type": None,
                "normalized": normalized,
            }

        if country in merged_extras:
            if not merged_extra_flags.get(country, False):
                return {
                    "allowed": False,
                    "reason": f"{country} calling is disabled",
                    "country": country,
                    "line_type": None,
                    "normalized": normalized,
                }
            extra_cfg = merged_extras.get(country) if isinstance(merged_extras.get(country), dict) else {}
            if extra_cfg.get("allow_any_prefix"):
                return {
                    "allowed": True,
                    "reason": None,
                    "country": country,
                    "line_type": "custom",
                    "normalized": normalized,
                }
            mobile_prefixes = extra_cfg.get("mobile_prefixes") if isinstance(extra_cfg.get("mobile_prefixes"), list) else []
            landline_prefixes = extra_cfg.get("landline_prefixes") if isinstance(extra_cfg.get("landline_prefixes"), list) else []
            if _prefix_match(national, mobile_prefixes):
                return {
                    "allowed": True,
                    "reason": None,
                    "country": country,
                    "line_type": "mobile",
                    "normalized": normalized,
                }
            if _prefix_match(national, landline_prefixes):
                return {
                    "allowed": True,
                    "reason": None,
                    "country": country,
                    "line_type": "landline",
                    "normalized": normalized,
                }
            return {
                "allowed": False,
                "reason": f"Can't call this number — not on the {country} call allow list",
                "country": country,
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
        allowlist, enabled, extras, extra_enabled, _removed = TelnyxPhoneAllowlistService.load(db)
        return TelnyxPhoneAllowlistService.validate_phone(
            phone,
            allowlist=allowlist,
            enabled=enabled,
            extras=extras,
            extra_enabled=extra_enabled,
        )

    @staticmethod
    def admin_view(cfg: dict[str, Any] | None) -> dict[str, Any]:
        allowlist, enabled, extras, extra_enabled, removed = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg or {})
        return {
            "phone_allowlist": allowlist,
            "phone_allowlist_enabled": enabled,
            "phone_allowlist_extra": extras,
            "phone_allowlist_extra_enabled": extra_enabled,
            "phone_allowlist_removed": removed,
            "defaults": DEFAULT_PHONE_ALLOWLIST,
            "defaults_extra": DEFAULT_PHONE_ALLOWLIST_EXTRA,
        }

    @staticmethod
    def parse_allowlist_json(raw: str) -> dict[str, Any]:
        parsed = json.loads(raw or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Allow list must be a JSON object")
        return _merge_allowlist(parsed)

    @staticmethod
    def order_requires_allowlist(db: Session, order: Any) -> bool:
        import json

        from app.services.platform_catalog_service import PlatformCatalogService

        if getattr(order, "service_code", None) == "survey":
            try:
                cfg = json.loads(getattr(order, "config_json", None) or "{}")
            except json.JSONDecodeError:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            return PlatformCatalogService.resolve_survey_channel(cfg) == "ai_call"
        if getattr(order, "service_code", None) == "interview":
            try:
                cfg = json.loads(getattr(order, "config_json", None) or "{}")
            except json.JSONDecodeError:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            delivery = PlatformCatalogService.normalize_interview_delivery(db, str(cfg.get("delivery") or "ai_call"))
            return delivery == "ai_call"
        return False

    @staticmethod
    def dialable_recipient_counts(db: Session, order: Any) -> dict[str, int]:
        from app.services.platform_catalog_service import ServiceOrderService

        if not TelnyxPhoneAllowlistService.order_requires_allowlist(db, order):
            total = max(0, int(getattr(order, "recipient_count", 0) or 0))
            return {"total": total, "dialable": total, "blocked": 0}
        recipients = ServiceOrderService.get_recipients(db, order.id)
        dialable = 0
        blocked = 0
        for recipient in recipients:
            phone = str(recipient.phone or "").strip()
            if not phone:
                blocked += 1
                continue
            check = TelnyxPhoneAllowlistService.validate_phone_db(db, phone)
            if check.get("allowed"):
                dialable += 1
            else:
                blocked += 1
        return {"total": len(recipients), "dialable": dialable, "blocked": blocked}
