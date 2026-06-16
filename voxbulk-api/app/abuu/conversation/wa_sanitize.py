"""Strip internal metadata from customer-facing WhatsApp text."""

from __future__ import annotations

import re

_ID_PATTERN = re.compile(r"\s*\[id=[^\]]+\]", re.IGNORECASE)
_REST_ID_PATTERN = re.compile(r"\s*\[restaurant_id=[^\]]+\]", re.IGNORECASE)
_SLUG_PATTERN = re.compile(r"\babuu-rest-[a-z0-9-]+\b", re.IGNORECASE)
_VOICE_PREFIX = re.compile(
    r"^\[(?:Voice note transcript|رسالة صوتية)[^\]]*\]\s*",
    re.IGNORECASE,
)


def wa_customer_sanitize(text: str) -> str:
    """Remove IDs, slugs, and debug markers from outbound WhatsApp copy."""
    cleaned = str(text or "")
    cleaned = _VOICE_PREFIX.sub("", cleaned)
    cleaned = _ID_PATTERN.sub("", cleaned)
    cleaned = _REST_ID_PATTERN.sub("", cleaned)
    cleaned = _SLUG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
