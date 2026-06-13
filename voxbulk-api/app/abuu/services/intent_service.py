"""Regex intent stub for Abuu WhatsApp ordering."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AbuuIntent:
    name: str
    item_ref: str | None = None


_START_PATTERNS = (
    re.compile(r"(?i)\babuu\b"),
    re.compile(r"(?i)\border\s+food\b"),
    re.compile(r"(?i)\bstart\s+order\b"),
    re.compile(r"طلب"),
    re.compile(r"طعام"),
    re.compile(r"اطلب"),
    re.compile(r"أكل"),
    re.compile(r"اكل"),
)

_CONFIRM_PATTERNS = (
    re.compile(r"(?i)^\s*(confirm|yes|done|checkout)\s*$"),
    re.compile(r"^\s*(تأكيد|نعم|تمام|انهاء|إنهاء)\s*$"),
)

_CANCEL_PATTERNS = (
    re.compile(r"(?i)^\s*(cancel|stop)\s*$"),
    re.compile(r"^\s*(الغاء|إلغاء|الغِ)\s*$"),
)

_MENU_PATTERNS = (
    re.compile(r"(?i)^\s*(menu|help)\s*$"),
    re.compile(r"^\s*(قائمة|مساعدة|منيو)\s*$"),
)


def detect_intent(text: str, *, has_active_session: bool) -> AbuuIntent:
    normalized = str(text or "").strip()
    if not normalized:
        return AbuuIntent("empty")

    for pattern in _CANCEL_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("cancel")

    for pattern in _CONFIRM_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("confirm")

    for pattern in _MENU_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("menu")

    if re.fullmatch(r"\d{1,2}", normalized):
        return AbuuIntent("add_item", item_ref=normalized)

    if not has_active_session:
        for pattern in _START_PATTERNS:
            if pattern.search(normalized):
                return AbuuIntent("order_food")

    if has_active_session:
        return AbuuIntent("add_item", item_ref=normalized)

    return AbuuIntent("unknown")


def is_abuu_start_message(text: str) -> bool:
    return detect_intent(text, has_active_session=False).name == "order_food"
