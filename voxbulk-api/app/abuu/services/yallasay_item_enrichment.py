"""Explicit recipes and allergen metadata for YallaSay catalog items."""

from __future__ import annotations

import json
from typing import Any

from app.abuu.menu_intelligence.vocabulary import dump_json_tags
from app.abuu.models.entities import RestaurantMenuItem

# Items that always carry tree-nut / peanut risk for demo allergy testing.
NUTS_ITEM_KEYS: frozenset[str] = frozenset(
    {
        "baklava-mix",
        "basbousa",
        "qatayef",
        "kunafa-portion",
        "kunafa-icecream",
        "chocolate-cake",
        "chocolate-cake-slice",
        "brownie",
        "warm-brownie",
        "cheesecake",
        "cheese-cake",
        "chocolate-shake",
        "loaded-fries",
    }
)

# Extra allergens beyond rule inference (item_key -> tags).
EXPLICIT_ALLERGENS: dict[str, list[str]] = {
    "mozzarella-sticks": ["dairy", "gluten", "eggs"],
    "caesar-salad": ["dairy", "gluten", "eggs"],
    "hummus-side": ["sesame"],
    "falafel-wrap": ["gluten", "sesame"],
    "shrimp-skewers": ["shellfish"],
    "fish-rice": ["fish", "shellfish"],
    "chocolate-shake": ["dairy"],
    "vanilla-shake": ["dairy"],
    "strawberry-shake": ["dairy"],
    "avocado-juice": ["dairy"],
    "um-ali": ["dairy", "eggs", "nuts"],
    "sahlab": ["dairy"],
    "rice-pudding": ["dairy"],
}

# Bilingual ingredient / recipe text keyed by catalog item key.
RECIPES: dict[str, tuple[str, str]] = {
    "charcoal-half": (
        "Half chicken, garlic, lemon, olive oil, seven spices. Charcoal grilled until golden.",
        "نصف دجاج، ثوم، ليمون، زيت زيتون، سبع بهارات. مشوي على الفحم حتى يتحمر.",
    ),
    "charcoal-quarter": (
        "Quarter chicken, garlic marinade, lemon, mixed spices. Charcoal grilled.",
        "ربع دجاج، تتبيلة ثوم، ليمون، بهارات مشكلة. مشوي على الفحم.",
    ),
    "shawarma-plate": (
        "Marinated chicken shawarma, garlic sauce, pickles, fries, pita bread.",
        "شاورما دجاج متبلة، صلصة ثوم، مخلل، بطاطا، خبز.",
    ),
    "shawarma-wrap": (
        "Chicken shawarma strips, tahini, pickles, tomatoes, wrapped in flatbread.",
        "شرائح شاورما دجاج، طحينة، مخلل، طماطم، ملفوفة بخبز عربي.",
    ),
    "grilled-wings": (
        "Chicken wings, paprika, garlic, lemon, charcoal grilled (6 pieces).",
        "أجنحة دجاج، بابريكا، ثوم، ليمون، مشوية على الفحم (6 قطع).",
    ),
    "crispy-strips": (
        "Chicken breast strips, seasoned flour, fried until crispy (5 pieces).",
        "شرائح صدر دجاج، دقيق متبل، مقلية حتى تصبح مقرمشة (5 قطع).",
    ),
    "classic-burger": (
        "Beef patty, lettuce, tomato, onion, pickles, burger bun, house sauce.",
        "قطعة لحم، خس، طماطم، بصل، مخلل، خبز برجر، صلصة خاصة.",
    ),
    "cheese-burger": (
        "Beef patty, cheddar cheese, lettuce, tomato, pickles, burger bun.",
        "قطعة لحم، جبنة شيدر، خس، طماطم، مخلل، خبز برجر.",
    ),
    "crispy-chicken-burger": (
        "Crispy fried chicken fillet, lettuce, mayo, pickles, sesame bun.",
        "فيليه دجاج مقرمش، خس، مايونيز، مخلل، خبز بالسمسم.",
    ),
    "mixed-grill": (
        "Kafta, shish tawook, lamb kebab, grilled tomatoes, onions, rice or bread.",
        "كفتة، شيش طاووق، كباب لحم، طماطم مشوية، بصل، أرز أو خبز.",
    ),
    "grilled-fish": (
        "Fresh sea bream, lemon, garlic, olive oil, herbs. Grilled whole.",
        "سمك دنيس طازج، ليمون، ثوم، زيت زيتون، أعشاب. مشوي كاملاً.",
    ),
    "shrimp-skewers": (
        "Marinated shrimp, garlic, lemon, grilled on skewers.",
        "روبيان متبل، ثوم، ليمون، مشوي على أسياخ.",
    ),
    "veggie-bowl": (
        "Grilled zucchini, eggplant, peppers, chickpeas, tahini drizzle.",
        "كوسا مشوية، باذنجان، فلفل، حمص، رشة طحينة.",
    ),
    "falafel-wrap": (
        "Falafel balls, tahini, salad, pickles, wrapped in flatbread.",
        "فلافل، طحينة، سلطة، مخلل، ملفوف بخبز عربي.",
    ),
    "beef-shawarma-wrap": (
        "Beef shawarma, tahini, pickles, sumac onions, flatbread wrap.",
        "شاورما لحم، طحينة، مخلل، بصل بالسماق، خبز لف.",
    ),
    "baklava-mix": (
        "Phyllo layers, pistachios, walnuts, clarified butter, orange blossom syrup.",
        "طبقات عجين، فستق، جوز، سمن، قطر بالزهر.",
    ),
    "kunafa-portion": (
        "Shredded kataifi, sweet cheese filling, pistachios, sugar syrup.",
        "شعيرية كنافة، حشوة جبنة حلوة، فستق، قطر.",
    ),
    "basbousa": (
        "Semolina cake, coconut, almonds, sugar syrup.",
        "كيك سميد، جوز الهند، لوز، قطر.",
    ),
    "qatayef": (
        "Stuffed pancakes with nuts and sweet cheese, fried and soaked in syrup (3 pcs).",
        "قطايف محشية مكسرات وجبنة، مقلية ومنقوعة بالقطر (3 قطع).",
    ),
    "chocolate-cake": (
        "Chocolate sponge, cocoa buttercream; may contain traces of nuts.",
        "كيك شوكولاتة، كريمة زبدة الكاكao؛ قد يحتوي على آثار مكسرات.",
    ),
    "cheesecake": (
        "Cream cheese, digestive biscuit base, vanilla; contains dairy and eggs.",
        "جبنة كريمية، قاعدة بسكويت، فانيلا؛ يحتوي على ألبان وبيض.",
    ),
    "brownie": (
        "Dark chocolate, butter, eggs, flour; may contain walnuts.",
        "شوكولاتة داكنة، زبدة، بيض، دقيق؛ قد يحتوي على جوز.",
    ),
    "coca-cola": ("Carbonated cola drink, served chilled.", "مشروب كولا غازي، يُقدّم بارداً."),
    "orange-juice": ("Freshly squeezed oranges, no added sugar.", "برتقال طازج معصور، بدون سكر مضاف."),
}


def _default_recipe(item_key: str, item_spec: dict[str, Any]) -> tuple[str, str]:
    name_en = str(item_spec.get("name_en") or item_key).strip()
    name_ar = str(item_spec.get("name_ar") or name_en).strip()
    desc_en = str(item_spec.get("description_en") or "").strip()
    desc_ar = str(item_spec.get("description_ar") or "").strip()
    if desc_en:
        return desc_en, desc_ar or desc_en
    return (
        f"Prepared fresh to order: {name_en}.",
        f"يُحضّر طازجاً عند الطلب: {name_ar}.",
    )


def resolve_allergens(item_key: str, inferred: dict[str, Any]) -> list[str]:
    tags = {str(t).strip().lower() for t in (inferred.get("allergen_tags") or []) if str(t).strip()}
    tags.update(str(t).strip().lower() for t in EXPLICIT_ALLERGENS.get(item_key, []) if str(t).strip())
    if item_key in NUTS_ITEM_KEYS:
        tags.add("nuts")
    return sorted(tags)


def resolve_dietary(inferred: dict[str, Any]) -> list[str]:
    tags = [str(t).strip().lower() for t in (inferred.get("dietary_tags") or []) if str(t).strip()]
    return sorted({t for t in tags if t != "halal"})


def resolve_recipe(item_key: str, item_spec: dict[str, Any]) -> tuple[str, str]:
    if item_key in RECIPES:
        return RECIPES[item_key]
    return _default_recipe(item_key, item_spec)


def apply_yallasay_item_enrichment(
    row: RestaurantMenuItem,
    *,
    item_key: str,
    item_spec: dict[str, Any],
    inferred: dict[str, Any],
    force: bool = True,
) -> bool:
    """Write allergens, dietary (no halal), and bilingual recipe onto a menu row."""
    changed = False
    allergens = resolve_allergens(item_key, inferred)
    dietary = resolve_dietary(inferred)
    recipe_en, recipe_ar = resolve_recipe(item_key, item_spec)

    allergen_json = dump_json_tags(allergens)
    dietary_json = dump_json_tags(dietary)
    ingredients_payload = json.dumps(
        {"ingredients_en": recipe_en, "ingredients_ar": recipe_ar},
        ensure_ascii=False,
    )

    if force or not row.allergen_tags_json:
        if row.allergen_tags_json != allergen_json:
            row.allergen_tags_json = allergen_json
            changed = True
    if force or not row.dietary_tags_json:
        if row.dietary_tags_json != dietary_json:
            row.dietary_tags_json = dietary_json
            changed = True
    if force or not row.ingredients_json:
        if row.ingredients_json != ingredients_payload:
            row.ingredients_json = ingredients_payload
            changed = True
    return changed
