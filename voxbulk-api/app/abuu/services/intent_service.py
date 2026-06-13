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

_RESTAURANT_LIST_PATTERNS = (
    re.compile(r"(?i)\b(restaurants?|show restaurants?|nearby|list restaurants?)\b"),
    re.compile(r"مطاعم"),
    re.compile(r"المطاعم"),
    re.compile(r"ورّني مطاعم"),
    re.compile(r"اعرض مطاعم"),
)

_SHOW_MORE_PATTERNS = (
    re.compile(r"(?i)^\s*(more|show more|next)\s*$"),
    re.compile(r"^\s*(المزيد|more|التالي)\s*$"),
)

_ORDER_STATUS_PATTERNS = (
    re.compile(r"(?i)\b(order status|where is my order|track order|my order)\b"),
    re.compile(r"حالة الطلب"),
    re.compile(r"وين طلبي"),
    re.compile(r"طلبي"),
)


def detect_intent(text: str, *, has_active_session: bool, step: str | None = None) -> AbuuIntent:
    normalized = str(text or "").strip()
    if not normalized:
        return AbuuIntent("empty")

    if step == "awaiting_name":
        if any(pattern.search(normalized) for pattern in _CANCEL_PATTERNS):
            return AbuuIntent("cancel")
        return AbuuIntent("provide_name", item_ref=normalized)

    for pattern in _CANCEL_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("cancel")

    for pattern in _CONFIRM_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("confirm")

    for pattern in _MENU_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("menu")

    for pattern in _ORDER_STATUS_PATTERNS:
        if pattern.search(normalized):
            return AbuuIntent("order_status")

    if re.fullmatch(r"\d{1,2}", normalized):
        return AbuuIntent("add_item", item_ref=normalized)

    if not has_active_session:
        for pattern in _START_PATTERNS:
            if pattern.search(normalized):
                return AbuuIntent("order_food")

    if has_active_session or step in {"awaiting_preference", "browsing"}:
        return AbuuIntent("add_item", item_ref=normalized)

    return AbuuIntent("unknown")


def is_abuu_start_message(text: str) -> bool:
    return detect_intent(text, has_active_session=False).name == "order_food"


def is_restaurant_list_message(text: str) -> bool:
    normalized = str(text or "").strip()
    return any(p.search(normalized) for p in _RESTAURANT_LIST_PATTERNS)


def is_show_more_message(text: str) -> bool:
    normalized = str(text or "").strip()
    return any(p.search(normalized) for p in _SHOW_MORE_PATTERNS)
