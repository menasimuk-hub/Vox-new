"""Supported meeting room languages — extend this list to add more."""

from __future__ import annotations

from typing import Any

MEETING_ROOM_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "label": "English"},
    {"code": "ar", "label": "Arabic"},
    {"code": "fr", "label": "French"},
]

DEFAULT_MEETING_ROOM_LANGUAGE = "en"


def meeting_room_language_options() -> list[dict[str, str]]:
    return list(MEETING_ROOM_LANGUAGES)


def normalize_meeting_room_language_code(raw: str | None) -> str:
    code = str(raw or DEFAULT_MEETING_ROOM_LANGUAGE).strip().lower()
    allowed = {str(row["code"]).strip().lower() for row in MEETING_ROOM_LANGUAGES}
    if code not in allowed:
        raise ValueError(f"Unsupported meeting room language: {raw}")
    return code


def meeting_room_language_label(code: str) -> str:
    clean = str(code or "").strip().lower()
    for row in MEETING_ROOM_LANGUAGES:
        if str(row.get("code") or "").strip().lower() == clean:
            return str(row.get("label") or clean)
    return clean
