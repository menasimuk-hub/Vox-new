"""Deterministic usage / help request detection."""

from __future__ import annotations

import re

from app.abuu.voice_interpretation.normalize import normalize_query

_USAGE_HELP_PATTERNS = (
    re.compile(r"(?i)^\s*help\s*$"),
    re.compile(r"^\s*مساعدة\s*$"),
    re.compile(r"^\s*مساعده\s*$"),
)


def is_usage_help_request(text: str) -> bool:
    """Whole-message help only — not «help me» or escalation phrases."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.search(r"(?i)\bhelp\s+me\b", raw):
        return False
    if re.search(r"عاجل|شكوى|مدير|دعم", normalize_query(raw, "ar")):
        return False
    normalized = normalize_query(raw, "ar")
    return any(p.search(normalized) or p.search(raw) for p in _USAGE_HELP_PATTERNS)
