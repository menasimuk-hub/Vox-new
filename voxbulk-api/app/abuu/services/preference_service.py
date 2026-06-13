"""Deterministic food-category matching for Abuu WhatsApp ordering."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FoodCategoryMatch:
    category: str
    keyword: str


_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "chicken": (
        r"(?i)\bchicken\b",
        r"دجاج",
        r"فراخ",
        r"فروج",
    ),
    "fish": (
        r"(?i)\b(fish|seafood|salmon|tuna)\b",
        r"سمك",
        r"بحري",
        r"أسماك",
    ),
    "meat": (
        r"(?i)\b(meat|beef|lamb|grill|kebab|steak)\b",
        r"لحم",
        r"مشاوي",
        r"كباب",
        r"برجر",
    ),
    "salad": (
        r"(?i)\b(salad|salads)\b",
        r"سلطة",
        r"سلطات",
        r"خضار",
    ),
    "drinks": (
        r"(?i)\b(drink|drinks|juice|water|coffee|tea|soda)\b",
        r"مشروب",
        r"مشروبات",
        r"عصير",
        r"ماء",
    ),
    "dessert": (
        r"(?i)\b(dessert|desserts|sweet|cake|ice cream)\b",
        r"حلو",
        r"حلويات",
        r"حلوى",
        r"كيك",
    ),
    "vegetarian": (
        r"(?i)\b(vegetarian|vegan|veggie|falafel)\b",
        r"نباتي",
        r"نباتية",
        r"فلافل",
        r"أخضر",
    ),
    "chips": (
        r"(?i)\b(chips|fries|french fries|potato)\b",
        r"بطاط",
        r"فرايز",
        r"بطاطا",
    ),
}

_CATEGORY_ITEM_TYPES: dict[str, set[str]] = {
    "chicken": {"meat", "food"},
    "fish": {"meat", "food"},
    "meat": {"meat", "food"},
    "salad": {"salad", "food", "sides"},
    "drinks": {"drink", "drinks"},
    "dessert": {"desserts", "food", "sides"},
    "vegetarian": {"food", "salad", "sides", "meat"},
    "chips": {"food", "sides", "addon"},
}

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chicken": ("chicken", "دجاج", "فراخ", "فروج"),
    "fish": ("fish", "seafood", "salmon", "tuna", "سمك", "بحري", "أسماك"),
    "meat": ("meat", "beef", "lamb", "grill", "kebab", "steak", "لحم", "مشawi", "مشاوي", "كباب"),
    "salad": ("salad", "salads", "سلطة", "سلطات"),
    "drinks": ("drink", "drinks", "juice", "water", "coffee", "tea", "مشروب", "عصير", "ماء"),
    "dessert": ("dessert", "sweet", "cake", "حلو", "حلويات", "حلوى"),
    "vegetarian": ("vegetarian", "vegan", "falafel", "نباتي", "فلافل", "خضار"),
    "chips": ("chips", "fries", "potato", "بطاط", "فرايز", "بطاطا"),
}


def match_food_categories(text: str) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    matched: list[str] = []
    for category, patterns in _CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized):
                if category not in matched:
                    matched.append(category)
                break
    return matched


def item_types_for_categories(categories: list[str]) -> set[str]:
    types: set[str] = set()
    for category in categories:
        types.update(_CATEGORY_ITEM_TYPES.get(category, set()))
    return types or {"meat", "food", "drink", "drinks", "salad", "sides", "desserts"}


def category_keywords(category: str) -> tuple[str, ...]:
    return _CATEGORY_KEYWORDS.get(category, ())


def category_label(category: str, lang: str) -> str:
    labels = {
        "chicken": ("Chicken", "دجاج"),
        "fish": ("Fish", "سمك"),
        "meat": ("Meat", "لحم"),
        "salad": ("Salad", "سلطة"),
        "drinks": ("Drinks", "مشروبات"),
        "dessert": ("Dessert", "حلويات"),
        "vegetarian": ("Vegetarian", "نباتي"),
        "chips": ("Chips / Fries", "بطاطا"),
    }
    en, ar = labels.get(category, (category.title(), category))
    return en if lang == "en" else ar
