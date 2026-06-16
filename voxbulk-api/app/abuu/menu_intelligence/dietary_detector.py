"""Detect dietary restrictions and allergies from customer text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.abuu.menu_intelligence.arabic_lexicon import normalize_arabizi


_ALLERGY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dairy", re.compile(r"(?i)\b(dairy|lactose|milk|cheese)\b|حليب|ألبان|جبن|بدون حليب|من دون حليب")),
    ("nuts", re.compile(r"(?i)\b(nut|nuts|peanut|almond)\b|مكسرات|فستق|فول سوداني|لوز|حساسية.*مكسر")),
    ("sesame", re.compile(r"(?i)\b(sesame|tahini)\b|سمسم|طحينة|حساسية.*سمسم")),
    ("gluten", re.compile(r"(?i)\b(gluten|celiac)\b|جلوتين|قمح|خالي من الجلوتين|بدون جلوتين")),
    ("shellfish", re.compile(r"(?i)\b(shellfish|shrimp|prawn)\b|محار|جمبري|قشريات")),
    ("fish", re.compile(r"(?i)\b(fish allergy)\b|حساسية.*سمك")),
]

_DIETARY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("vegan", re.compile(r"(?i)\b(vegan)\b|نباتي|vegan|plant.?based|بدون لحم")),
    ("vegetarian", re.compile(r"(?i)\b(vegetarian|veggie)\b|نباتية|خضار فقط")),
    ("halal", re.compile(r"(?i)\b(halal)\b|حلال")),
    ("gluten_free", re.compile(r"(?i)\b(gluten.?free)\b|خالي من الجلوتين")),
    ("sugar_free", re.compile(r"(?i)\b(sugar.?free|no sugar)\b|بدون سكر|خالي من السكر")),
]

_NO_SPICY = re.compile(r"(?i)\b(no spicy|not spicy|mild only)\b|بدون حار|ما بدي حار|غير حار")


@dataclass
class DietaryDetection:
    allergens_avoid: list[str]
    dietary_tags: list[str]
    kitchen_note: str | None = None
    is_allergy_declared: bool = False


class DietaryDetector:
    @staticmethod
    def detect(text: str) -> DietaryDetection:
        normalized = normalize_arabizi(str(text or "").strip())
        allergens: list[str] = []
        dietary: list[str] = []
        is_allergy = bool(re.search(r"(?i)\ballerg|حساسية", normalized))

        for tag, pattern in _ALLERGY_PATTERNS:
            if pattern.search(normalized) and tag not in allergens:
                allergens.append(tag)
        for tag, pattern in _DIETARY_PATTERNS:
            if pattern.search(normalized) and tag not in dietary:
                dietary.append(tag)
        if _NO_SPICY.search(normalized) and "mild" not in dietary:
            dietary.append("no_spicy")

        note = None
        if allergens:
            note = "Allergy: " + ", ".join(allergens)
        elif dietary:
            note = "Diet: " + ", ".join(d for d in dietary if d != "no_spicy")

        return DietaryDetection(
            allergens_avoid=allergens,
            dietary_tags=[d for d in dietary if d in {"vegan", "vegetarian", "halal", "gluten_free", "sugar_free"}],
            kitchen_note=note,
            is_allergy_declared=is_allergy or bool(allergens),
        )
