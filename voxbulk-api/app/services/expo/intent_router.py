"""Hybrid Expo intent router — corrections and product requests without free-form LLM chat."""

from __future__ import annotations

import re
from typing import Any

# Field the visitor wants to correct while a follow-up value is pending.
PENDING_CORRECTION_KEY = "pending_correction_field"

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"[\d+().\-\s]{7,}")

_CHANGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b(?:change|update|fix|edit|correct|wrong)\b.{0,24}\b(?:e[\-\s]?mail|email)\b", re.I)),
    ("email", re.compile(r"\b(?:e[\-\s]?mail|email)\b.{0,16}\b(?:is wrong|incorrect|change|update)\b", re.I)),
    ("phone", re.compile(r"\b(?:change|update|fix|edit|correct|wrong)\b.{0,24}\b(?:phone|mobile|number|tel)\b", re.I)),
    ("phone", re.compile(r"\b(?:phone|mobile|number)\b.{0,16}\b(?:is wrong|incorrect|change|update)\b", re.I)),
    ("name", re.compile(r"\b(?:change|update|fix|edit|correct|wrong)\b.{0,24}\b(?:my\s+)?name\b", re.I)),
    ("company", re.compile(r"\b(?:change|update|fix|edit|correct|wrong)\b.{0,24}\b(?:company|organisation|organization|firm)\b", re.I)),
]

_LIST_PRODUCTS = re.compile(
    r"(?:\b(?:list|show)\b.{0,30}\b(?:your|the|all|our|any|available|me)\b.{0,24}\b(?:products?|catalogue|catalog|brochures?|files?|pdfs?)\b)"
    r"|(?:\b(?:what|which)\b.{0,40}\b(?:products?|catalogue|catalog|brochures?|files?)\b)"
    r"|(?:\b(?:products?|catalogue|catalog)\b.{0,20}\b(?:list|have|available)\b)",
    re.I,
)
_SEND_ALL = re.compile(
    r"\b(?:send|give|email)\b.{0,30}\b(?:all|everything|every)\b"
    r"|\b(?:all|everything)\b.{0,20}\b(?:products?|files?|catalogue|catalog|pdfs?)\b"
    r"|\bboth\b",
    re.I,
)
_SKIP = re.compile(r"^\s*(?:skip|pass|n/?a|none|no comment|nothing)\s*$", re.I)


def detect_intent(text: str) -> dict[str, Any] | None:
    """Return an intent dict or None if the message should continue the normal step flow."""
    clean = str(text or "").strip()
    if not clean:
        return None

    if _SKIP.match(clean):
        return {"intent": "skip"}

    for field, pat in _CHANGE_PATTERNS:
        if pat.search(clean):
            value = _extract_inline_value(field, clean)
            out: dict[str, Any] = {"intent": f"change_{field}", "field": field}
            if value:
                out["value"] = value
            return out

    if _SEND_ALL.search(clean):
        return {"intent": "send_all"}
    if _LIST_PRODUCTS.search(clean):
        return {"intent": "list_products"}

    return None


def _extract_inline_value(field: str, text: str) -> str | None:
    lower = text.lower()
    for sep in (" to ", " is ", ":", "="):
        if sep in lower:
            # Use last occurrence after a change verb when possible
            idx = lower.rfind(sep)
            candidate = text[idx + len(sep) :].strip(" .,\"'")
            if candidate:
                if field == "email":
                    m = _EMAIL_RE.search(candidate)
                    return m.group(0) if m else None
                if field == "phone":
                    m = _PHONE_RE.search(candidate)
                    return re.sub(r"[^\d+]", "", m.group(0)) if m else None
                if len(candidate) >= 2:
                    return candidate[:255]
    if field == "email":
        m = _EMAIL_RE.search(text)
        return m.group(0) if m else None
    if field == "phone":
        m = _PHONE_RE.search(text)
        return re.sub(r"[^\d+]", "", m.group(0)) if m else None
    return None


def prompt_for_correction(field: str) -> str:
    prompts = {
        "email": "📧 What's the correct email address?",
        "phone": "📱 What's the correct mobile number?",
        "name": "👤 What's the correct full name?",
        "company": "🏢 What's the correct company name?",
    }
    return prompts.get(field, "Please send the corrected value.")


def apply_lead_field(lead: Any, field: str, value: str) -> str:
    """Mutate lead contact field; return confirmation snippet."""
    clean = str(value or "").strip()[:255]
    if field == "email":
        lead.visitor_email = clean
        return f"Email updated to {clean}."
    if field == "phone":
        digits = re.sub(r"[^\d+]", "", clean)
        lead.visitor_phone = digits or clean
        return f"Phone updated to {lead.visitor_phone}."
    if field == "name":
        lead.name = clean
        return f"Name updated to {clean}."
    if field == "company":
        lead.company = clean
        return f"Company updated to {clean}."
    return "Details updated."
