"""Detect visitor language from E.164 phone prefix."""

from __future__ import annotations

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
]


def detect_language_from_phone(phone: str) -> str:
    normalized = str(phone or "").strip()
    if not normalized.startswith("+"):
        normalized = f"+{normalized.lstrip('+')}"
    for prefix, lang in sorted(PREFIX_TO_LANGUAGE, key=lambda item: len(item[0]), reverse=True):
        if normalized.startswith(prefix):
            return lang
    return "en_GB"


def resolve_session_language(*, phone: str, trigger_hint: str | None = None) -> str:
    """Pick template language: explicit (ar) hint overrides phone prefix."""
    hint = str(trigger_hint or "").strip().lower().replace("-", "_")
    if hint in {"ar", "arabic"}:
        return "ar"
    if hint in {"en", "english", "en_gb", "en_us", "en_au"}:
        return "en_GB"
    phone_lang = detect_language_from_phone(phone)
    if phone_lang == "ar":
        return "ar"
    return "en_GB"
