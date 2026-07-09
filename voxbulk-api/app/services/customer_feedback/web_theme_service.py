"""Resolve web survey theme for Customer Feedback locations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

INDUSTRY_DEFAULT_THEME: dict[str, str] = {
    "restaurant": "restaurants-cafes",
    "retail": "retail-shops",
    "salon": "salons-spas",
    "hotel": "hotels-hospitality",
    "fitness": "fitness-gyms",
    "events": "events-entertainment",
    "others": "others",
}

OVERLAY_WINDOWS: dict[str, dict[str, str]] = {
    "survey-summer": {"from": "06-01", "to": "08-31"},
    "survey-winter": {"from": "12-01", "to": "02-28"},
    "christmas": {"from": "12-10", "to": "12-27"},
    "new-year": {"from": "12-28", "to": "01-05"},
    "valentines-day": {"from": "02-10", "to": "02-16"},
    "halloween": {"from": "10-25", "to": "11-01"},
}

OVERLAY_IDS = frozenset(
    {
        "survey-summer",
        "survey-winter",
        "island",
        "christmas",
        "new-year",
        "chinese-new-year",
        "valentines-day",
        "easter",
        "halloween",
        "thanksgiving",
        "diwali",
        "ramadan-eid",
        "eid-al-adha",
    }
)


def _mmdd(dt: datetime | None = None) -> str:
    now = dt or datetime.utcnow()
    return f"{now.month:02d}-{now.day:02d}"


def _in_window(today: str, start: str, end: str) -> bool:
    if start <= end:
        return start <= today <= end
    return today >= start or today <= end


def parse_web_theme_config(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_web_theme_from_location(location) -> dict[str, Any]:
    config = parse_web_theme_config(getattr(location, "survey_config_json", None))
    web_theme = config.get("web_theme")
    return web_theme if isinstance(web_theme, dict) else {}


def default_theme_for_industry(industry_slug: str | None) -> str:
    if not industry_slug:
        return "survey-temp"
    return INDUSTRY_DEFAULT_THEME.get(industry_slug, "survey-temp")


def active_overlay_id(web_theme: dict[str, Any], *, now: datetime | None = None) -> str | None:
    overlay_ids = web_theme.get("overlay_ids") or []
    if not isinstance(overlay_ids, list) or not overlay_ids:
        return None
    mode = str(web_theme.get("overlay_mode") or "auto")
    if mode == "fixed":
        for oid in overlay_ids:
            clean = str(oid or "").strip()
            if clean:
                return clean
        return None
    today = _mmdd(now)
    for oid in overlay_ids:
        clean = str(oid or "").strip()
        if not clean:
            continue
        window = OVERLAY_WINDOWS.get(clean)
        if window and _in_window(today, window["from"], window["to"]):
            return clean
        if not window and clean in OVERLAY_IDS:
            return clean
    return None


def resolve_theme_id(
    *,
    industry_slug: str | None,
    web_theme: dict[str, Any] | None = None,
    theme_id: str | None = None,
    now: datetime | None = None,
) -> str:
    cfg = web_theme or {}
    base_pick = str(theme_id or cfg.get("base_template_id") or "auto").strip()
    base = default_theme_for_industry(industry_slug) if base_pick in {"", "auto"} else base_pick
    overlay = active_overlay_id(cfg, now=now)
    return overlay or base


def merge_web_theme_into_config(config: dict[str, Any], web_theme: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(config or {})
    if web_theme:
        out["web_theme"] = web_theme
    return out
