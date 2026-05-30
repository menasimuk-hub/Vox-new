from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import InstrumentedAttribute

# Admin zone keys: gb, us, ca, au
ZONE_LABELS: dict[str, str] = {
    "gb": "United Kingdom",
    "us": "United States",
    "ca": "Canada",
    "au": "Australia",
}

ZONE_CURRENCY: dict[str, str] = {
    "gb": "£",
    "us": "$",
    "ca": "CA$",
    "au": "A$",
}

_COUNTRY_TO_ZONE: dict[str, str] = {
    "united kingdom": "gb",
    "uk": "gb",
    "gb": "gb",
    "great britain": "gb",
    "england": "gb",
    "scotland": "gb",
    "wales": "gb",
    "northern ireland": "gb",
    "united states": "us",
    "usa": "us",
    "us": "us",
    "u.s.": "us",
    "u.s.a.": "us",
    "canada": "ca",
    "ca": "ca",
    "australia": "au",
    "au": "au",
}


def normalize_zone(zone: str | None) -> str | None:
    if not zone:
        return None
    z = str(zone).strip().lower()
    if z in ("gb", "uk"):
        return "gb"
    if z in ZONE_LABELS:
        return z
    return None


def country_to_zone(country: str | None) -> str:
    key = str(country or "United Kingdom").strip().lower()
    return _COUNTRY_TO_ZONE.get(key, "gb")


def zone_label(zone: str | None) -> str:
    z = normalize_zone(zone) or country_to_zone(zone)
    return ZONE_LABELS.get(z, ZONE_LABELS["gb"])


def zone_currency_symbol(zone: str | None) -> str:
    z = normalize_zone(zone) or country_to_zone(zone)
    return ZONE_CURRENCY.get(z, "£")


def format_wallet_pence(pence: int, zone: str | None) -> str:
    sym = zone_currency_symbol(zone)
    return f"{sym}{(max(0, int(pence or 0)) / 100):.2f}"


def country_column_matches_zone(country_col: InstrumentedAttribute, zone: str) -> or_:
    """SQL filter for organisation.country matching an admin zone."""
    z = normalize_zone(zone)
    if z is None:
        raise ValueError(f"Unknown zone: {zone}")

    normalized = func.lower(func.trim(func.coalesce(country_col, "")))
    if z == "gb":
        keys = ("united kingdom", "uk", "gb", "great britain", "england", "scotland", "wales", "northern ireland")
    elif z == "us":
        keys = ("united states", "usa", "us", "u.s.", "u.s.a.")
    elif z == "ca":
        keys = ("canada", "ca")
    else:
        keys = ("australia", "au")

    return or_(*[normalized == k for k in keys])
