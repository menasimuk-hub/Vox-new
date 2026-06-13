"""Deterministic add-on suggestions after main item selection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.models.entities import RestaurantMenuItem
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import format_shekel, localized_name


_ADDON_KEYWORDS: dict[str, tuple[str, ...]] = {
    "salad": ("salad", "سلطة", "tabbouleh", "fattoush", "خضار"),
    "drink": ("drink", "juice", "water", "cola", "tea", "coffee", "مشروب", "عصير", "ماء", "كولا"),
    "chips": ("fries", "chips", "potato", "بطاط", "فرايز"),
    "dessert": ("dessert", "sweet", "cake", "حلو", "كيك"),
}


def _addon_types_for_main(item_type: str, categories: list[str]) -> list[str]:
    cats = set(categories or [])
    if "fish" in cats or item_type in {"food"} and any(k in cats for k in ("fish",)):
        return ["chips", "drink"]
    if "chicken" in cats or "meat" in cats or item_type in {"meat", "food"}:
        return ["salad", "drink"]
    if "vegetarian" in cats or item_type == "salad":
        return ["drink", "dessert"]
    return ["drink", "dessert"]


def _find_addon_items(
    db: Session,
    restaurant_id: str,
    addon_kinds: list[str],
    *,
    exclude_ids: set[str],
    limit: int = 2,
) -> list[RestaurantMenuItem]:
    rows = AbuuOrderDraftService.list_addon_items(db, restaurant_id, limit=30)
    found: list[RestaurantMenuItem] = []
    for kind in addon_kinds:
        keywords = _ADDON_KEYWORDS.get(kind, ())
        for item in rows:
            if item.id in exclude_ids or item.id in {i.id for i in found}:
                continue
            hay = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
            if any(kw in hay for kw in keywords) or item.item_type in {"addon", "drink", "drinks", "salad", "sides"}:
                if kind == "salad" and "salad" not in hay and item.item_type not in {"salad", "sides"}:
                    continue
                if kind == "chips" and not any(kw in hay for kw in _ADDON_KEYWORDS["chips"]):
                    continue
                found.append(item)
                break
        if len(found) >= limit:
            break
    return found[:limit]


def suggest_addons(
    db: Session,
    *,
    restaurant_id: str,
    main_item: RestaurantMenuItem,
    active_categories: list[str],
    context: dict,
    lang: str,
) -> tuple[str | None, dict]:
    already = set(context.get("last_addon_suggestions") or [])
    cart_ids = set(context.get("cart_item_ids") or [])
    exclude = already | cart_ids

    kinds = _addon_types_for_main(main_item.item_type or "food", active_categories)
    items = _find_addon_items(db, restaurant_id, kinds, exclude_ids=exclude, limit=2)
    if not items:
        return None, context

    labels = [localized_name(item, lang) for item in items]
    prices = [format_shekel(item.price_agorot) for item in items]
    parts = [f"{label} ({price})" for label, price in zip(labels, prices)]
    joined = ", ".join(parts)
    if lang == "en":
        msg = f"Would you like to add {joined}? Reply with the item name."
    else:
        msg = f"هل تريد إضافة {joined}؟ أرسل اسم الصنف."

    context = dict(context)
    suggested_ids = [item.id for item in items]
    context["last_addon_suggestions"] = list(already | set(suggested_ids))
    context["pending_addon_items"] = [{"menu_item_id": i.id, "name_en": i.name_en, "name_ar": i.name_ar} for i in items]
    return msg, context
