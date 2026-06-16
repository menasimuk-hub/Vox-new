"""Shared food-ordering policy — proceed with suggestions when intent is clear."""

from __future__ import annotations

PROTEIN_CATEGORIES = frozenset({"chicken", "fish", "meat"})
FOOD_CATEGORIES = frozenset(
    {"chicken", "fish", "meat", "salad", "drinks", "dessert", "vegetarian", "chips", "offers"}
)
CONFLICTING_PROTEINS = frozenset({frozenset({"chicken", "fish"}), frozenset({"chicken", "meat"}), frozenset({"fish", "meat"})})

_GENERIC_CLARIFY_PHRASES = (
    "ممكن توضّح",
    "توضّح شو بدك",
    "could you clarify",
    "what would you like",
    "what do you want",
)


def food_categories(hints: list[str] | None) -> list[str]:
    return [h for h in (hints or []) if h in FOOD_CATEGORIES]


def extract_food_query(
    text: str,
    *,
    protected_tokens: list[str] | None = None,
    category_hints: list[str] | None = None,
) -> str:
    tokens = [t for t in (protected_tokens or []) if t]
    if tokens:
        return " ".join(tokens)
    hints = food_categories(category_hints)
    if len(hints) == 1:
        return hints[0]
    normalized = str(text or "").strip()
    for word in normalized.split():
        if word in {"دجاج", "سمك", "لحم", "كولا", "شاورما", "chicken", "fish", "meat", "cola", "shawarma"}:
            return word
    return normalized


def has_strong_food_signal(
    *,
    protected_tokens: list[str] | None = None,
    category_hints: list[str] | None = None,
    stt_confidence: float = 1.0,
    min_stt: float = 0.65,
) -> bool:
    if protected_tokens:
        return float(stt_confidence or 0.0) >= min_stt
    cats = food_categories(category_hints)
    if len(cats) == 1 and float(stt_confidence or 0.0) >= min_stt:
        return True
    return False


def proteins_conflict(category_hints: list[str] | None) -> bool:
    cats = set(food_categories(category_hints))
    proteins = cats & PROTEIN_CATEGORIES
    if len(proteins) < 2:
        return False
    return proteins in CONFLICTING_PROTEINS or len(proteins) >= 2


def dominant_categories(categories: list[str] | None) -> list[str]:
    """Pick categories to search when LLM/heuristics return multiple labels."""
    cats = food_categories(categories)
    if not cats:
        return []
    if len(cats) == 1:
        return cats
    proteins = [c for c in cats if c in PROTEIN_CATEGORIES]
    if len(proteins) == 1:
        return proteins
    if proteins_conflict(cats):
        return cats
    # Prefer first protein/drink over side categories like salad/chips noise
    for preferred in ("chicken", "fish", "meat", "drinks", "dessert", "vegetarian"):
        if preferred in cats:
            return [preferred]
    return [cats[0]]


def should_block_turn_for_clarification(
    *,
    reason: str | None,
    protected_tokens: list[str] | None = None,
    category_hints: list[str] | None = None,
    stt_confidence: float = 1.0,
) -> bool:
    """True only when we should stop the turn and send a clarification message."""
    if not reason:
        return False
    if reason in {"allergy_uncertain", "item_ambiguous", "category_ambiguous", "stt_low_quality"}:
        return True
    if reason == "low_confidence" and has_strong_food_signal(
        protected_tokens=protected_tokens,
        category_hints=category_hints,
        stt_confidence=stt_confidence,
    ):
        return False
    if reason == "low_confidence" and food_categories(category_hints):
        return False
    return reason == "low_confidence"


def is_generic_clarify_reply(text: str) -> bool:
    low = str(text or "").lower()
    return any(p in low for p in _GENERIC_CLARIFY_PHRASES)
