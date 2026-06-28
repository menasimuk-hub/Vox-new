"""Detect script language from user input for interview generation and moderation."""

from __future__ import annotations

import re

from app.constants.meeting_room_languages import DEFAULT_MEETING_ROOM_LANGUAGE, meeting_room_language_label

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_FRENCH_HINT_RE = re.compile(
    r"\b(le|la|les|des|une|est|pour|avec|vous|nous|très|être|avoir|candidat|poste)\b",
    re.I,
)

_SUPPORTED = frozenset({"en", "ar", "fr"})


def normalize_script_language_code(raw: str | None) -> str:
    code = str(raw or DEFAULT_MEETING_ROOM_LANGUAGE).strip().lower()
    if code in _SUPPORTED:
        return code
    return DEFAULT_MEETING_ROOM_LANGUAGE


def detect_script_language(text: str, *, override: str | None = None) -> str:
    """Return en, ar, or fr from text heuristics; optional override wins when valid."""
    if override:
        clean = str(override).strip().lower()
        if clean in _SUPPORTED:
            return clean

    sample = str(text or "").strip()
    if not sample:
        return DEFAULT_MEETING_ROOM_LANGUAGE

    arabic_chars = len(_ARABIC_RE.findall(sample))
    latin_chars = len(_LATIN_RE.findall(sample))
    letter_total = arabic_chars + latin_chars
    if letter_total == 0:
        return DEFAULT_MEETING_ROOM_LANGUAGE

    arabic_ratio = arabic_chars / letter_total
    if arabic_ratio >= 0.25:
        return "ar"

    if latin_chars > 0 and _FRENCH_HINT_RE.search(sample) and arabic_chars == 0:
        french_markers = len(_FRENCH_HINT_RE.findall(sample))
        if french_markers >= 2:
            return "fr"

    return DEFAULT_MEETING_ROOM_LANGUAGE


def script_language_label(code: str) -> str:
    return meeting_room_language_label(normalize_script_language_code(code))
