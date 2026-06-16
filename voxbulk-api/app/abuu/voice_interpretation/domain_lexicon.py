"""Restaurant-domain synonyms and common STT confusion variants."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.abuu.voice_interpretation.fuzzy_match import fuzzy_score
from app.abuu.voice_interpretation.normalize import normalize_query


@dataclass(frozen=True)
class LexiconEntry:
    canonical: str
    category: str | None
    phrases: tuple[str, ...]


# canonical token → category hint (food_search categories)
_LEXICON: tuple[LexiconEntry, ...] = (
    LexiconEntry("دجاج", "chicken", ("دجاج", "دجاجج", "djaj", "dajaj", "dijaj", "chicken", "فراخ", "فراخه")),
    LexiconEntry("سمك", "fish", ("سمك", "سمكك", "samak", "fish", "seafood", "بحري")),
    LexiconEntry("لحم", "meat", ("لحم", "lahm", "meat", "beef", "burger", "برجر")),
    LexiconEntry("مشروبات", "drinks", ("مشروب", "مشروبات", "mshrob", "mshrobt", "drink", "drinks", "عصير", "juice", "cola", "كولا", "water", "ماء")),
    LexiconEntry("حلويات", "dessert", ("حلو", "حلويات", "حلوى", "dessert", "sweet", "cake", "kunafa", "كناف")),
    LexiconEntry("سلطة", "salad", ("سلطه", "سلطة", "salad", "tabbouleh", "تبوله")),
    LexiconEntry("شاورما", None, ("شاورما", "shawarma", "shwarma")),
    LexiconEntry("عرض", "offers", ("عرض", "عروض", "3arod", "3orod", "offer", "combo", "bundle")),
    LexiconEntry("نباتي", "vegetarian", ("نباتي", "nabati", "vegan", "vegetarian", "veggie")),
    LexiconEntry("حار", None, ("حار", "spicy", "hot")),
)

_ALLERGY_UNCERTAIN = re.compile(r"(?i)\b(allerg|حساسيه|حساسية)\b")
_ALLERGY_CLEAR = re.compile(
    r"(?i)(حساسيه|حساسية|allerg).{0,25}(حليب|dairy|lactose|مكسر|nut|peanut|فول سوداني|سمسم|sesame|جلوت|gluten|قشري|shellfish|سمك)"
)


def lexicon_correct(text: str, *, language: str = "ar", min_score: int = 72) -> tuple[str, list[str], float]:
    """Return corrected text, inferred categories, correction confidence."""
    normalized = normalize_query(text, language)
    if not normalized:
        return text, [], 0.0

    tokens = normalized.split()
    corrected_tokens: list[str] = []
    categories: list[str] = []
    scores: list[float] = []

    for token in tokens:
        best_entry: LexiconEntry | None = None
        best_score = 0
        for entry in _LEXICON:
            for phrase in entry.phrases:
                score = fuzzy_score(token, normalize_query(phrase, language))
                if score > best_score:
                    best_score = score
                    best_entry = entry
        if best_entry and best_score >= min_score:
            corrected_tokens.append(best_entry.canonical)
            if best_entry.category and best_entry.category not in categories:
                categories.append(best_entry.category)
            scores.append(best_score / 100.0)
        else:
            corrected_tokens.append(token)

    whole_categories = list(categories)
    for entry in _LEXICON:
        for phrase in entry.phrases:
            if fuzzy_score(normalized, normalize_query(phrase, language)) >= min_score:
                if entry.category and entry.category not in whole_categories:
                    whole_categories.append(entry.category)

    corrected = " ".join(corrected_tokens).strip() or normalized
    conf = sum(scores) / len(scores) if scores else (0.5 if whole_categories else 0.3)
    return corrected, whole_categories, min(1.0, conf)


def detect_allergy_uncertainty(text: str) -> bool:
    normalized = normalize_query(text, "ar")
    if _ALLERGY_CLEAR.search(normalized):
        return False
    return bool(_ALLERGY_UNCERTAIN.search(normalized))
