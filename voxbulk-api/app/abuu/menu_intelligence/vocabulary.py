"""Canonical menu tag and item_type vocabulary."""

from __future__ import annotations

CANONICAL_ITEM_TYPES = frozenset(
    {
        "meal",
        "sandwich",
        "platter",
        "drink",
        "dessert",
        "appetizer",
        "salad",
        "side",
        "sauce",
        "combo",
        "offer",
    }
)

LEGACY_ITEM_TYPE_MAP: dict[str, str] = {
    "food": "meal",
    "meat": "meal",
    "drinks": "drink",
    "desserts": "dessert",
    "addon": "side",
    "sides": "side",
}

DRINK_TYPES = frozenset({"drink", "drinks"})
DESSERT_TYPES = frozenset({"dessert", "desserts"})
MEAL_TYPES = frozenset({"meal", "food", "meat", "sandwich", "platter", "combo", "appetizer"})
OFFER_TYPES = frozenset({"offer", "combo"})
SIDE_TYPES = frozenset({"side", "sides", "addon", "sauce", "salad"})

ALLERGEN_TAGS = frozenset({"dairy", "nuts", "sesame", "gluten", "shellfish", "eggs", "soy", "fish"})
DIETARY_TAGS = frozenset({"vegetarian", "vegan", "halal", "gluten_free", "sugar_free"})
RECIPE_TAGS = frozenset({"grilled", "fried", "sweet", "baked", "raw", "spicy", "roasted", "steamed"})
DRINK_TAGS = frozenset({"iced", "hot", "juice", "soft_drink", "coffee", "tea", "shake", "water"})
PROTEIN_TAGS = frozenset({"chicken", "fish", "beef", "lamb", "plant", "seafood"})


def normalize_item_type(raw: str | None) -> str:
    value = str(raw or "meal").strip().lower()
    if value in CANONICAL_ITEM_TYPES:
        return value
    return LEGACY_ITEM_TYPE_MAP.get(value, value if value else "meal")


def parse_json_tags(raw: str | None, allowed: frozenset[str]) -> list[str]:
    if not raw:
        return []
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for entry in data:
        tag = str(entry or "").strip().lower()
        if tag and tag in allowed and tag not in out:
            out.append(tag)
    return out


def dump_json_tags(tags: list[str] | None) -> str | None:
    import json

    cleaned = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
    if not cleaned:
        return None
    return json.dumps(sorted(set(cleaned)))


def item_is_drink(item_type: str) -> bool:
    return normalize_item_type(item_type) == "drink" or item_type in DRINK_TYPES


def item_is_dessert(item_type: str) -> bool:
    t = normalize_item_type(item_type)
    return t == "dessert" or item_type in DESSERT_TYPES


def item_is_offer(item_type: str, offer_type: str | None = None) -> bool:
    t = normalize_item_type(item_type)
    return t in OFFER_TYPES or bool(str(offer_type or "").strip())
