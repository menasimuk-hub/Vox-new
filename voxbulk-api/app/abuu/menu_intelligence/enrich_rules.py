"""Rule-based tag inference for menu enrichment."""

from __future__ import annotations

from typing import Any

from app.abuu.menu_intelligence.vocabulary import dump_json_tags, normalize_item_type
from app.abuu.models.entities import RestaurantMenuItem


def _hay(*parts: str | None) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def infer_tags_for_item(
    *,
    cat_key: str,
    item_spec: dict[str, Any],
    profile: str | None = None,
) -> dict[str, Any]:
    """Return structured fields to merge onto RestaurantMenuItem."""
    name_en = item_spec.get("name_en") or ""
    name_ar = item_spec.get("name_ar") or ""
    desc_en = item_spec.get("description_en") or ""
    desc_ar = item_spec.get("description_ar") or ""
    raw_type = str(item_spec.get("item_type") or "meal")
    hay = _hay(name_en, name_ar, desc_en, desc_ar, cat_key)

    item_type = normalize_item_type(raw_type)
    offer_type = None
    if "combo" in hay or "وجبة" in hay or item_type == "combo":
        item_type = "combo" if "combo" in hay or "وجبة" in hay else item_type
        offer_type = "combo" if item_type in {"combo", "offer"} else offer_type

    if cat_key in {"soft-drinks", "juices", "hot-drinks"} or raw_type in {"drink", "drinks"}:
        item_type = "drink"
    elif cat_key in {"desserts", "sweets"} or raw_type in {"desserts", "dessert"}:
        item_type = "dessert"
    elif raw_type in {"sides", "addon"}:
        item_type = "side"
    elif raw_type in {"food", "meat"}:
        item_type = "meal"

    allergen_tags: list[str] = []
    dietary_tags: list[str] = []
    recipe_tags: list[str] = []
    protein_tags: list[str] = []
    drink_tags: list[str] = []

    if any(w in hay for w in ("grill", "charcoal", "مشوي", "فحم", "shawarma", "شاورما")):
        recipe_tags.append("grilled")
    if any(w in hay for w in ("crispy", "fried", "مقل", "مقرمش", "nugget", "ناجت")):
        recipe_tags.append("fried")
    if any(w in hay for w in ("sweet", "chocolate", "حلو", "كيك", "cake", "kunafa", "كناف")):
        recipe_tags.append("sweet")
    if any(w in hay for w in ("spicy", "hot", "حار", "har")):
        recipe_tags.append("spicy")

    if any(w in hay for w in ("cheese", "mozzarella", "جبن", "موزار")):
        allergen_tags.append("dairy")
    if any(w in hay for w in ("nut", "fistq", "فستق", "لوز", "almond")):
        allergen_tags.append("nuts")
    if any(w in hay for w in ("sesame", "tahini", "سمسم", "طحين")):
        allergen_tags.append("sesame")
    if any(w in hay for w in ("fish", "سمك", "seafood", "shrimp", "جمبري")):
        allergen_tags.append("fish")
        protein_tags.append("fish")
    if any(w in hay for w in ("shellfish", "shrimp", "جمبري", "محار")):
        allergen_tags.append("shellfish")
    if any(w in hay for w in ("bread", "burger", "برجر", "wrap", "ساند")):
        allergen_tags.append("gluten")

    if "veggie" in hay or "vegetarian" in hay or "نباتي" in hay:
        dietary_tags.append("vegetarian")
        protein_tags.append("plant")
    if "vegan" in hay:
        dietary_tags.append("vegan")
        protein_tags.append("plant")
    if "zero" in hay or "sugar-free" in hay or "زيرو" in hay:
        dietary_tags.append("sugar_free")

    if any(w in hay for w in ("chicken", "دجاج", "wings", "nugget")):
        protein_tags.append("chicken")
    if any(w in hay for w in ("beef", "لحم", "burger", "برجر")):
        protein_tags.append("beef")

    if item_type == "drink":
        if any(w in hay for w in ("juice", "shake", "عصير", "ميلك")):
            drink_tags.append("juice")
        elif any(w in hay for w in ("coffee", "tea", "قهو", "شاي")):
            drink_tags.append("coffee" if "coffee" in hay or "قهو" in hay else "tea")
        elif "water" in hay or "ماء" in hay:
            drink_tags.append("water")
        else:
            drink_tags.append("soft_drink")
        if "zero" in hay:
            drink_tags.append("iced")

    if profile == "vegetarian" or "vegetarian" in (profile or ""):
        if "veggie" in hay or "vegetarian" in hay or "نباتي" in hay:
            dietary_tags.append("vegetarian")

    # Gaza pilot default: halal unless explicitly fish-only sides
    if "halal" not in dietary_tags:
        dietary_tags.append("halal")

    category_kind = None
    if item_type == "drink":
        category_kind = "drink"
    elif item_type == "dessert":
        category_kind = "dessert"
    elif item_type in {"offer", "combo"}:
        category_kind = "offer"
    elif item_type == "side":
        category_kind = "side"
    else:
        category_kind = "meal"

    classified = bool(item_type and (allergen_tags or recipe_tags or dietary_tags or item_type in {"drink", "dessert"}))

    return {
        "item_type": item_type,
        "offer_type": offer_type,
        "category_kind": category_kind,
        "allergen_tags": sorted(set(allergen_tags)),
        "dietary_tags": sorted(set(dietary_tags)),
        "recipe_tags": sorted(set(recipe_tags)),
        "protein_tags": sorted(set(protein_tags)),
        "drink_tags": sorted(set(drink_tags)),
        "classification_status": "classified" if classified else "unclassified",
    }


def apply_inferred_tags(row: RestaurantMenuItem, inferred: dict, *, force: bool = False) -> bool:
    """Merge inferred tag fields onto a menu item row."""
    changed = False
    if force or not row.item_type or row.item_type in {"food", "meat", "drinks"}:
        if row.item_type != inferred["item_type"]:
            row.item_type = inferred["item_type"]
            changed = True
    if inferred.get("offer_type") and (force or not row.offer_type):
        row.offer_type = inferred["offer_type"]
        changed = True

    for field, key in (
        ("allergen_tags_json", "allergen_tags"),
        ("dietary_tags_json", "dietary_tags"),
        ("recipe_tags_json", "recipe_tags"),
        ("protein_tags_json", "protein_tags"),
        ("drink_tags_json", "drink_tags"),
    ):
        existing = getattr(row, field, None)
        if existing and not force:
            continue
        dumped = dump_json_tags(inferred.get(key))
        if dumped != existing:
            setattr(row, field, dumped)
            changed = True

    status = inferred.get("classification_status") or "unclassified"
    if force or row.classification_status in {None, "", "unclassified"}:
        if row.classification_status != status:
            row.classification_status = status
            changed = True
    return changed
