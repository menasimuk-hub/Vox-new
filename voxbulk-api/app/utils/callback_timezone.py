from __future__ import annotations

import re

DEFAULT_CALLBACK_TZ = "Europe/London"

_COUNTRY_TZ: dict[str, str] = {
    "uk": "Europe/London",
    "gb": "Europe/London",
    "gbr": "Europe/London",
    "united kingdom": "Europe/London",
    "great britain": "Europe/London",
    "england": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "northern ireland": "Europe/London",
    "australia": "Australia/Sydney",
    "au": "Australia/Sydney",
    "aus": "Australia/Sydney",
    "canada": "America/Toronto",
    "ca": "America/Toronto",
    "can": "America/Toronto",
}

# Canadian NANP area codes (partial list — Toronto default if unknown +1)
_CANADA_AREA_CODES = frozenset(
    {
        "204",
        "226",
        "236",
        "249",
        "250",
        "289",
        "306",
        "343",
        "365",
        "367",
        "403",
        "416",
        "418",
        "431",
        "437",
        "438",
        "450",
        "468",
        "474",
        "506",
        "514",
        "519",
        "548",
        "579",
        "581",
        "584",
        "587",
        "604",
        "613",
        "639",
        "647",
        "672",
        "705",
        "709",
        "742",
        "753",
        "778",
        "780",
        "782",
        "807",
        "819",
        "825",
        "867",
        "873",
        "879",
        "902",
        "905",
    }
)

_WESTERN_CANADA = frozenset({"250", "236", "604", "778", "587", "780", "825", "867", "403"})


def _normalize_country(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _digits(phone: str | None) -> str:
    raw = re.sub(r"\D", "", str(phone or ""))
    if raw.startswith("00"):
        return raw[2:]
    return raw


def timezone_from_country(country: str | None) -> str | None:
    key = _normalize_country(country)
    if not key:
        return None
    if key in _COUNTRY_TZ:
        return _COUNTRY_TZ[key]
    for token, tz in _COUNTRY_TZ.items():
        if len(token) > 2 and token in key:
            return tz
    return None


def timezone_from_phone(phone: str | None) -> str | None:
    digits = _digits(phone)
    if not digits:
        return None
    if digits.startswith("44"):
        return "Europe/London"
    if digits.startswith("61"):
        return "Australia/Sydney"
    if digits.startswith("1") and len(digits) >= 11:
        area = digits[1:4]
        if area in _CANADA_AREA_CODES:
            if area in _WESTERN_CANADA:
                return "America/Vancouver"
            if area in {"204", "306", "431", "639", "867"}:
                return "America/Winnipeg"
            if area in {"403", "587", "780", "825"}:
                return "America/Edmonton"
            return "America/Toronto"
    if digits.startswith("07") and len(digits) == 11:
        return "Europe/London"
    if digits.startswith("0") and len(digits) >= 10:
        return "Europe/London"
    return None


def resolve_callback_timezone(
    *,
    explicit: str | None = None,
    phone: str | None = None,
    country: str | None = None,
) -> str:
    tz = str(explicit or "").strip()
    if tz:
        return tz
    from_country = timezone_from_country(country)
    if from_country:
        return from_country
    from_phone = timezone_from_phone(phone)
    if from_phone:
        return from_phone
    return DEFAULT_CALLBACK_TZ
