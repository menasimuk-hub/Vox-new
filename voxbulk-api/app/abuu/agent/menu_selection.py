"""Canonical numbered menu index for all Abuu ordering paths."""

from __future__ import annotations

from typing import Any

from app.abuu.agent.session import Session as AgentSession
from app.abuu.models.entities import RestaurantMenuItem
from app.abuu.services.reply_service import format_shekel, localized_name, menu_keyboard_hint


def build_menu_item_index(items: list[RestaurantMenuItem]) -> list[dict[str, Any]]:
    return [
        {
            "index": idx,
            "id": item.id,
            "name_en": item.name_en,
            "name_ar": item.name_ar,
            "price_agorot": int(item.price_agorot or 0),
        }
        for idx, item in enumerate(items, start=1)
    ]


def store_shown_menu(
    session: AgentSession,
    items: list[RestaurantMenuItem],
    *,
    source: str = "menu",
) -> list[dict[str, Any]]:
    index = build_menu_item_index(items)
    session.context["menu_item_index"] = index
    session.context["suggested_items"] = [
        {"idx": row["index"], "menu_item_id": row["id"]} for row in index
    ]
    session.context["awaiting_dish_pick"] = True
    session.context["awaiting_restaurant_pick"] = False
    session.context["last_list_type"] = source
    return index


def format_numbered_menu_lines(
    items: list[RestaurantMenuItem],
    lang: str,
    *,
    header: str | None = None,
    limit: int | None = None,
    include_hint: bool = True,
) -> str:
    rows = items[:limit] if limit else items
    lines: list[str] = []
    if header:
        lines.append(header)
    for idx, item in enumerate(rows, start=1):
        label = localized_name(item, lang)
        lines.append(f"{idx}. {label} — {format_shekel(item.price_agorot)}")
    if include_hint:
        lines.append(menu_keyboard_hint(lang).strip())
    return "\n".join(lines)


def session_menu_filters(session: AgentSession) -> tuple[list[str], list[str]]:
    ctx = session.context or {}
    allergen_avoid = ctx.get("allergen_avoid") or []
    dietary_required = ctx.get("dietary_tags") or []
    avoid = [str(x) for x in allergen_avoid if x] if isinstance(allergen_avoid, list) else []
    diet = [str(x) for x in dietary_required if x] if isinstance(dietary_required, list) else []
    return avoid, diet
