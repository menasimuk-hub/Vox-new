"""Parse keyboard dish picks: 1 2 3 and 1*3 3*2."""

from __future__ import annotations

import re
from typing import Any

_ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PICK_TOKEN = re.compile(r"^(\d+)(?:[*×x](\d+))?$", re.I)


def normalize_pick_text(text: str) -> str:
    return str(text or "").strip().translate(_ARABIC_DIGIT_MAP)


def parse_menu_pick_tokens(text: str) -> list[tuple[int, int]] | None:
    """Return list of (menu_index, quantity) or None if text is not a pure pick message."""
    normalized = normalize_pick_text(text)
    if not normalized:
        return None
    parts = normalized.split()
    if not parts:
        return None
    picks: list[tuple[int, int]] = []
    for part in parts:
        match = _PICK_TOKEN.match(part)
        if not match:
            return None
        index = int(match.group(1))
        qty = int(match.group(2)) if match.group(2) else 1
        if index < 1 or qty < 1:
            return None
        picks.append((index, qty))
    return picks or None


def is_menu_pick_message(text: str) -> bool:
    return parse_menu_pick_tokens(text) is not None


def _index_lookup(menu_item_index: list[Any]) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for row in menu_item_index:
        if not isinstance(row, dict):
            continue
        idx = int(row.get("index") or 0)
        if idx > 0:
            lookup[idx] = row
    return lookup


def resolve_menu_picks_to_items(
    menu_item_index: list[Any],
    picks: list[tuple[int, int]],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Map picks to proposal rows; returns (items, invalid_indices)."""
    by_index = _index_lookup(menu_item_index)
    items: list[dict[str, Any]] = []
    invalid: list[int] = []
    for index, qty in picks:
        row = by_index.get(index)
        item_id = str(row.get("id") or "").strip() if row else ""
        if not item_id:
            invalid.append(index)
            continue
        items.append({"menu_item_id": item_id, "quantity": qty})
    return items, invalid
