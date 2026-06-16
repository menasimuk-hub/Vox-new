"""Protected vocabulary — category hints without destructive token replacement."""

from __future__ import annotations

from dataclasses import dataclass

from app.abuu.voice_interpretation.fuzzy_match import fuzzy_score
from app.abuu.waiter.normalization import normalize_query


@dataclass(frozen=True)
class ProtectedEntry:
    token: str
    category_hint: str | None
    protein_hint: str | None = None
    drink_hint: bool = False


_PROTECTED: tuple[ProtectedEntry, ...] = (
    ProtectedEntry("كولا", "drinks", drink_hint=True),
    ProtectedEntry("cola", "drinks", drink_hint=True),
    ProtectedEntry("دجاج", "chicken", protein_hint="chicken"),
    ProtectedEntry("chicken", "chicken", protein_hint="chicken"),
    ProtectedEntry("djaj", "chicken", protein_hint="chicken"),
    ProtectedEntry("سمك", "fish", protein_hint="fish"),
    ProtectedEntry("fish", "fish", protein_hint="fish"),
    ProtectedEntry("شاورما", None, protein_hint="chicken"),
    ProtectedEntry("shawarma", None, protein_hint="chicken"),
    ProtectedEntry("لحم", "meat", protein_hint="beef"),
    ProtectedEntry("meat", "meat", protein_hint="beef"),
    ProtectedEntry("مشروبات", "drinks", drink_hint=True),
    ProtectedEntry("drinks", "drinks", drink_hint=True),
    ProtectedEntry("حلويات", "dessert"),
    ProtectedEntry("dessert", "dessert"),
    ProtectedEntry("عرض", "offers"),
    ProtectedEntry("offers", "offers"),
    ProtectedEntry("نباتي", "vegetarian"),
    ProtectedEntry("vegan", "vegetarian"),
)


def detect_protected_tokens(text: str, *, language: str = "ar", min_score: int = 72) -> list[str]:
    normalized = normalize_query(text, language)
    found: list[str] = []
    for token in normalized.split():
        for entry in _PROTECTED:
            if fuzzy_score(token, normalize_query(entry.token, language)) >= min_score:
                if entry.token not in found:
                    found.append(entry.token)
                break
    return found


def category_hints_for_text(text: str, *, language: str = "ar") -> list[str]:
    normalized = normalize_query(text, language)
    hints: list[str] = []
    for token in normalized.split():
        best: ProtectedEntry | None = None
        best_score = 0
        for entry in _PROTECTED:
            score = fuzzy_score(token, normalize_query(entry.token, language))
            if score > best_score:
                best_score = score
                best = entry
        if best and best_score >= 72 and best.category_hint and best.category_hint not in hints:
            hints.append(best.category_hint)
    whole = normalized
    for entry in _PROTECTED:
        if fuzzy_score(whole, normalize_query(entry.token, language)) >= 72:
            if entry.category_hint and entry.category_hint not in hints:
                hints.append(entry.category_hint)
    return hints


def conservative_transcript(raw: str, *, language: str = "ar") -> str:
    """Return normalized text without replacing specific food tokens with category words."""
    from app.abuu.waiter.normalization import normalize_ordering_text

    return normalize_ordering_text(raw, language=language)


def token_must_not_map_to(source: str, forbidden: str) -> bool:
    """True if source token should never be rewritten as forbidden (e.g. دجاج -> لحم)."""
    src_hints = category_hints_for_text(source, language="ar")
    if forbidden in {"meat", "لحم"} and "chicken" in src_hints:
        return True
    if forbidden == "drinks" and any(t in detect_protected_tokens(source) for t in ("كولا", "cola")):
        return True
    return False
