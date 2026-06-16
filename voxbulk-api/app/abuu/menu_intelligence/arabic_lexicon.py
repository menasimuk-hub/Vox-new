"""Arabic-first lexicon and basic Arabizi normalization."""

from __future__ import annotations

import re

_ARABIZI_MAP = {
    "3ndak": "عندكم",
    "3ndk": "عندك",
    "mshrob": "مشروب",
    "mshrobt": "مشروبات",
    "7alab": "حليب",
    "7alba": "حليب",
    "samak": "سمك",
    "dajaj": "دجاج",
    "nabati": "نباتي",
    "3arod": "عرض",
    "3orod": "عروض",
}


def normalize_arabizi(text: str) -> str:
    lowered = str(text or "").lower()
    for latin, arabic in _ARABIZI_MAP.items():
        lowered = re.sub(rf"\b{re.escape(latin)}\b", arabic, lowered)
    return lowered


def expand_food_categories(text: str) -> list[str]:
    """Return extra category hints from Arabic/English colloquial phrases."""
    t = normalize_arabizi(text)
    cats: list[str] = []
    if re.search(r"مشروب|مشروبات|عصير|drink|juice|coffee|tea", t, re.I):
        cats.append("drinks")
    if re.search(r"حلو|حلويات|حلوى|dessert|sweet|cake", t, re.I):
        cats.append("dessert")
    if re.search(r"عرض|عروض|combo|offer|bundle", t, re.I):
        cats.append("offers")
    if re.search(r"سمك|fish|seafood|بحري", t, re.I):
        cats.append("fish")
    if re.search(r"دجاج|chicken|فراخ", t, re.I):
        cats.append("chicken")
    if re.search(r"نباتي|vegan|vegetarian", t, re.I):
        cats.append("vegetarian")
    return cats
