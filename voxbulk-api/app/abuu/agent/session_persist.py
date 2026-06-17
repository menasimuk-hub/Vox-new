"""Compact Abuu session context before MySQL/Redis persistence."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Rebuilt from DB on demand — do not persist in context_json.
_CONTEXT_VOLATILE_KEYS = frozenset(
    {
        "prefetched_restaurant_list",
        "prefetched_menu",
        "prefetched_offers",
        "ranked_restaurants",
        "turn_ranked_restaurants",
        "phase1_requested_restaurant_id",
        "menu_item_index",
    }
)

# Leave headroom under legacy MySQL TEXT (65535 bytes).
_CONTEXT_JSON_MAX_BYTES = 52_000


def truncate_messages(messages: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    if max_messages <= 0:
        return []
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def _truncate_message_content(
    messages: list[dict[str, Any]],
    *,
    max_chars: int = 1500,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = str(msg.get("content") or "")
        if len(content) > max_chars:
            content = content[: max_chars - 1] + "…"
        out.append({**msg, "content": content})
    return out


def compact_context_for_persist(
    context: dict[str, Any] | None,
    *,
    max_history: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    max_hist = max_history if max_history is not None else settings.abuu_agent_max_history

    ctx = dict(context or {})
    for key in _CONTEXT_VOLATILE_KEYS:
        ctx.pop(key, None)

    messages = ctx.get("messages")
    if isinstance(messages, list):
        cleaned = [m for m in messages if isinstance(m, dict)]
        ctx["messages"] = _truncate_message_content(truncate_messages(cleaned, max_hist))

    last_search = ctx.get("last_food_search")
    if isinstance(last_search, list) and len(last_search) > 12:
        ctx["last_food_search"] = last_search[-12:]

    suggested = ctx.get("suggested_items")
    if isinstance(suggested, list) and len(suggested) > 24:
        ctx["suggested_items"] = suggested[:24]

    return ctx


def _context_json_bytes(context: dict[str, Any]) -> int:
    return len(json.dumps(context, ensure_ascii=False).encode("utf-8"))


def fit_context_json_size(
    context: dict[str, Any],
    *,
    max_bytes: int = _CONTEXT_JSON_MAX_BYTES,
) -> dict[str, Any]:
    """Progressively shrink context until JSON fits under max_bytes."""
    ctx = dict(context)
    if _context_json_bytes(ctx) <= max_bytes:
        return ctx

    while _context_json_bytes(ctx) > max_bytes:
        messages = ctx.get("messages")
        if isinstance(messages, list) and len(messages) > 2:
            ctx["messages"] = messages[2:]
            continue

        stripped = False
        for key in ("last_food_search", "suggested_items", "active_categories"):
            if key in ctx:
                ctx.pop(key, None)
                stripped = True
                break
        if stripped:
            continue

        if isinstance(messages, list) and messages:
            ctx["messages"] = [
                {**m, "content": str(m.get("content") or "")[:400]}
                for m in messages
                if isinstance(m, dict)
            ]
            if _context_json_bytes(ctx) <= max_bytes:
                return ctx

        logger.warning(
            "abuu_context_json_still_oversized bytes=%s keys=%s",
            _context_json_bytes(ctx),
            sorted(ctx.keys()),
        )
        return ctx

    return ctx


def prepare_context_for_storage(context: dict[str, Any] | None) -> dict[str, Any]:
    compact = compact_context_for_persist(context)
    return fit_context_json_size(compact)


def strip_volatile_context_keys(context: dict[str, Any] | None) -> None:
    if not context:
        return
    for key in _CONTEXT_VOLATILE_KEYS:
        context.pop(key, None)
