"""Arabic and mixed-language text normalization for voice transcripts."""

from __future__ import annotations

import re

from app.abuu.menu_intelligence.arabic_lexicon import normalize_arabizi

_FILLER_WORDS = frozenset(
    {
        "please",
        "pls",
        "ya3ni",
        "يعني",
        "بدي",
        "bade",
        "badde",
        "badi",
        "abi",
        "عايز",
        "عاوز",
        "please",
        "um",
        "uh",
    }
)


def normalize_ar(text: str) -> str:
    cleaned = str(text or "").strip().lower()
    cleaned = re.sub(r"[\u064B-\u065F\u0670]", "", cleaned)
    cleaned = cleaned.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return cleaned


def normalize_query(text: str, language: str) -> str:
    if language == "ar" or re.search(r"[\u0600-\u06FF]", str(text or "")):
        return normalize_ar(normalize_arabizi(text))
    return normalize_arabizi(str(text or "").strip().lower())


def normalize_ordering_text(text: str, *, language: str = "ar") -> str:
    """Full pipeline: Arabizi → Arabic normalize → dedupe tokens → strip fillers."""
    normalized = normalize_query(text, language)
    tokens = [t for t in re.split(r"\s+", normalized) if t]
    deduped: list[str] = []
    for tok in tokens:
        if tok in _FILLER_WORDS:
            continue
        if deduped and deduped[-1] == tok:
            continue
        deduped.append(tok)
    return " ".join(deduped).strip()
