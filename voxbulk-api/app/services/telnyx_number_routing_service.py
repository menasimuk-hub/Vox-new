"""Resolve Telnyx outbound voice / WhatsApp sender by destination region."""

from __future__ import annotations

from typing import Any

from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService


def _norm_regions(raw: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        token = str(item or "").strip().lower()
        if not token:
            continue
        if token == "eu":
            out.append("eu")
        elif len(token) == 2:
            out.append(token.upper())
        elif token == "global":
            out.append("global")
        else:
            out.append(token)
    return out


def _normalize_route_row(row: dict[str, Any]) -> dict[str, Any] | None:
    number = str(row.get("number") or "").strip()
    if not number:
        return None
    try:
        number = normalize_telnyx_e164(number)
    except ValueError:
        return None
    regions = _norm_regions(row.get("regions"))
    if not regions:
        regions = ["global"]
    label = str(row.get("label") or "").strip()
    return {"number": number, "regions": regions, "label": label}


def normalize_route_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_route_row(row)
        if not normalized or normalized["number"] in seen:
            continue
        seen.add(normalized["number"])
        out.append(normalized)
    return out


def seed_routes_from_legacy(config: dict[str, Any]) -> dict[str, Any]:
    """Populate voice/whatsapp route arrays from legacy single-number fields when empty."""
    cfg = {**config}
    voice = normalize_route_list(cfg.get("voice_routes"))
    if not voice:
        legacy = str(cfg.get("default_outbound_number") or cfg.get("from_phone_number") or "").strip()
        if legacy:
            try:
                legacy = normalize_telnyx_e164(legacy)
                voice = [{"number": legacy, "regions": ["global"], "label": "Legacy voice"}]
            except ValueError:
                pass
    wa = normalize_route_list(cfg.get("whatsapp_routes"))
    if not wa:
        legacy_wa = str(cfg.get("whatsapp_from") or cfg.get("whatsapp_number") or "").strip()
        if legacy_wa:
            try:
                legacy_wa = normalize_telnyx_e164(legacy_wa)
                wa = [{"number": legacy_wa, "regions": ["global"], "label": "Legacy WhatsApp"}]
            except ValueError:
                pass
    cfg["voice_routes"] = voice
    cfg["whatsapp_routes"] = wa
    return cfg


def destination_region(e164: str, *, config: dict[str, Any] | None = None) -> str | None:
    cfg = config or {}
    allowlist, _, extras, extra_enabled = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg)
    country, _ = TelnyxPhoneAllowlistService._detect_country(
        e164,
        allowlist,
        extras=extras,
        extra_enabled=extra_enabled,
    )
    if not country:
        return None
    return str(country).lower()


def _region_tokens(region: str | None) -> set[str]:
    if not region:
        return set()
    r = str(region).strip().lower()
    if r in {"usa", "us"}:
        return {"us", "usa", "global"}
    if r in {"ca", "canada"}:
        return {"ca", "global"}
    if r in {"gb", "uk"}:
        return {"gb", "uk", "global"}
    if r in {"au", "australia"}:
        return {"au", "global"}
    if r == "eu":
        return {"eu", "global"}
    return {r, "global"}


def _route_matches(route: dict[str, Any], dest_tokens: set[str]) -> bool:
    route_regions = {str(x).strip().lower() for x in (route.get("regions") or [])}
    if "global" in route_regions:
        return True
    expanded: set[str] = set()
    for reg in route_regions:
        expanded |= _region_tokens(reg)
    return bool(dest_tokens & expanded)


def resolve_from_routes(
    routes: list[dict[str, Any]],
    *,
    destination_e164: str | None,
    fallback: str | None,
    config: dict[str, Any] | None = None,
) -> str | None:
    normalized_routes = normalize_route_list(routes)
    if not normalized_routes:
        return fallback or None
    dest_region = destination_region(destination_e164 or "", config=config) if destination_e164 else None
    dest_tokens = _region_tokens(dest_region)
    exact = [
        r
        for r in normalized_routes
        if dest_region
        and _route_matches(r, {dest_region})
        and "global" not in {str(x).lower() for x in (r.get("regions") or [])}
    ]
    if exact:
        return str(exact[0]["number"])
    regional = [r for r in normalized_routes if dest_tokens and _route_matches(r, dest_tokens)]
    if regional:
        return str(regional[0]["number"])
    global_routes = [r for r in normalized_routes if "global" in {str(x).lower() for x in (r.get("regions") or [])}]
    if global_routes:
        return str(global_routes[0]["number"])
    return str(normalized_routes[0]["number"]) or fallback


class TelnyxNumberRoutingService:
    @staticmethod
    def resolve_voice_from(*, destination_e164: str | None, config: dict[str, Any]) -> str | None:
        cfg = seed_routes_from_legacy(config)
        fallback = telnyx_outbound_caller_id(cfg)
        return resolve_from_routes(
            cfg.get("voice_routes") or [],
            destination_e164=destination_e164,
            fallback=fallback,
            config=cfg,
        )

    @staticmethod
    def resolve_whatsapp_from(*, destination_e164: str | None, config: dict[str, Any]) -> str | None:
        cfg = seed_routes_from_legacy(config)
        fallback = str(cfg.get("whatsapp_from") or cfg.get("whatsapp_number") or "").strip() or None
        return resolve_from_routes(
            cfg.get("whatsapp_routes") or [],
            destination_e164=destination_e164,
            fallback=fallback,
            config=cfg,
        )

    @staticmethod
    def resolve_sms_from(*, destination_e164: str | None, config: dict[str, Any]) -> str | None:
        cfg = seed_routes_from_legacy(config)
        fallback = str(cfg.get("sms_from") or "").strip() or None
        sms_routes = cfg.get("sms_routes") or cfg.get("whatsapp_routes") or []
        return resolve_from_routes(
            sms_routes,
            destination_e164=destination_e164,
            fallback=fallback,
            config=cfg,
        )
