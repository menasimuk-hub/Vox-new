"""Detect visitor language from E.164 phone prefix and venue country."""

from __future__ import annotations

import re

PREFIX_TO_LANGUAGE: list[tuple[str, str]] = [
    ("+44", "en_GB"),
    ("+1", "en_US"),
    ("+61", "en_AU"),
    ("+33", "fr"),
    ("+49", "de"),
    ("+34", "es"),
    ("+39", "it"),
    ("+351", "pt"),
    ("+31", "nl"),
    ("+48", "pl"),
    ("+90", "tr"),
    ("+91", "hi"),
    ("+86", "zh_CN"),
    ("+81", "ja"),
    ("+82", "ko"),
    ("+966", "ar"),
    ("+971", "ar"),
    ("+974", "ar"),
    ("+973", "ar"),
    ("+968", "ar"),
    ("+965", "ar"),
    ("+962", "ar"),
    ("+961", "ar"),
    ("+964", "ar"),
    ("+967", "ar"),
    ("+970", "ar"),
    ("+20", "ar"),
    ("+212", "ar"),
    ("+213", "ar"),
    ("+216", "ar"),
]

# Venue / QR sender country (Admin zone or ISO) → template language fallback.
LOCATION_COUNTRY_TO_LANGUAGE: dict[str, str] = {
    "gb": "en_GB",
    "uk": "en_GB",
    "us": "en_US",
    "ca": "en_GB",
    "au": "en_AU",
    "eu": "en_GB",
    "ae": "ar",
    "sa": "ar",
    "ps": "ar",
    "qa": "ar",
    "kw": "ar",
    "bh": "ar",
    "om": "ar",
    "jo": "ar",
    "lb": "ar",
    "iq": "ar",
    "ye": "ar",
    "eg": "ar",
    "ma": "ar",
    "dz": "ar",
    "tn": "ar",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "nl": "nl",
    "pl": "pl",
    "tr": "tr",
}


def normalize_feedback_phone(phone: str) -> str:
    """E.164 for prefix matching (handles WhatsApp numbers without leading +)."""
    raw = str(phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return "+"
    return f"+{digits}"


def detect_language_from_phone(phone: str) -> str:
    lang, _matched = detect_language_from_phone_with_match(phone)
    return lang


def detect_language_from_phone_with_match(phone: str) -> tuple[str, bool]:
    normalized = normalize_feedback_phone(phone)
    for prefix, lang in sorted(PREFIX_TO_LANGUAGE, key=lambda item: len(item[0]), reverse=True):
        if normalized.startswith(prefix):
            return lang, True
    return "en_GB", False


def language_from_location_country(country: str | None) -> str | None:
    key = str(country or "").strip().lower()
    if not key:
        return None
    if key in LOCATION_COUNTRY_TO_LANGUAGE:
        return LOCATION_COUNTRY_TO_LANGUAGE[key]
    if len(key) == 2 and key.isalpha():
        return LOCATION_COUNTRY_TO_LANGUAGE.get(key)
    return None


def normalize_session_language(lang: str | None) -> str:
    """Map detected locale to FeedbackWaTemplate.language codes."""
    code = str(lang or "en_GB").strip().lower().replace("-", "_")
    if code in {"ar", "arabic"}:
        return "ar"
    if code.startswith("en"):
        if code in {"en_us", "en_usa"}:
            return "en_US"
        if code in {"en_au"}:
            return "en_AU"
        return "en_GB"
    canonical = {
        "fr": "fr",
        "de": "de",
        "es": "es",
        "it": "it",
        "pt": "pt_PT",
        "pt_pt": "pt_PT",
        "pt_br": "pt_BR",
        "nl": "nl",
        "pl": "pl",
        "tr": "tr",
        "hi": "hi",
        "zh_cn": "zh_CN",
        "zh": "zh_CN",
        "ja": "ja",
        "ko": "ko",
        "bn": "bn",
        "ru": "ru",
        "ur": "ur",
        "ro": "ro",
        "el": "el",
        "sv": "sv",
        "cs": "cs",
        "nb": "nb",
        "no": "nb",
    }
    return canonical.get(code, "en_GB")


def map_stt_language_code(stt_code: str | None) -> str | None:
    """Map Whisper/DeepInfra/Deepgram detected language codes to session locale."""
    raw = str(stt_code or "").strip().lower().replace("-", "_")
    if not raw or raw in {"auto", "unknown", "multi", "und"}:
        return None
    name_map = {
        "english": "en",
        "arabic": "ar",
        "french": "fr",
        "spanish": "es",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",
        "dutch": "nl",
        "polish": "pl",
        "turkish": "tr",
        "hindi": "hi",
        "japanese": "ja",
        "korean": "ko",
        "chinese": "zh_CN",
        "irish": "en_GB",
    }
    if raw in name_map:
        raw = name_map[raw]
    if raw.startswith("en"):
        return normalize_session_language(raw)
    mapped = normalize_session_language(raw)
    return mapped if mapped else None


def resolve_session_language(
    *,
    phone: str,
    trigger_hint: str | None = None,
    location_country: str | None = None,
) -> str:
    """Pick template language: QR hint → phone prefix → venue country → en_GB."""
    hint = str(trigger_hint or "").strip().lower().replace("-", "_")
    if hint in {"ar", "arabic"}:
        return "ar"
    if hint in {"en", "english", "en_gb", "en_us", "en_au"}:
        return normalize_session_language(hint)

    phone_lang, matched = detect_language_from_phone_with_match(phone)
    if matched:
        return normalize_session_language(phone_lang)

    location_lang = language_from_location_country(location_country)
    if location_lang:
        return normalize_session_language(location_lang)

    return normalize_session_language(phone_lang)
