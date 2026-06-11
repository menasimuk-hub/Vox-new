from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.services.billing_currency import EU_MEMBER_STATES
from app.services.country_vat_service import _COUNTRY_ALIASES

# Admin zone keys: gb, eu, us, ca, au
ZONE_LABELS: dict[str, str] = {
    "gb": "United Kingdom",
    "eu": "Eurozone",
    "us": "United States",
    "ca": "Canada",
    "au": "Australia",
}

ZONE_CURRENCY: dict[str, str] = {
    "gb": "£",
    "eu": "€",
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
    "eurozone": "eu",
    "eu": "eu",
    "europe": "eu",
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

_EU_COUNTRY_KEYS = tuple(
    sorted(
        key
        for key, code in _COUNTRY_ALIASES.items()
        if code in EU_MEMBER_STATES
    )
)


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
    if key in _COUNTRY_TO_ZONE:
        return _COUNTRY_TO_ZONE[key]
    code = _COUNTRY_ALIASES.get(key)
    if not code and len(key) == 2 and key.isalpha():
        code = key.upper()
    if code and code in EU_MEMBER_STATES:
        return "eu"
    return "gb"


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
    elif z == "eu":
        keys = ("eurozone", "eu", "europe", *_EU_COUNTRY_KEYS)
    elif z == "us":
        keys = ("united states", "usa", "us", "u.s.", "u.s.a.")
    elif z == "ca":
        keys = ("canada", "ca")
    else:
        keys = ("australia", "au")

    return or_(*[normalized == k for k in keys])
