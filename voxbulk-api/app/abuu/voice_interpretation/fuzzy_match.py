"""Shared fuzzy matching utilities (extracted from agent kb)."""

from __future__ import annotations

from typing import Any

from app.abuu.voice_interpretation.normalize import normalize_ar, normalize_query


def fuzzy_score(a: str, b: str) -> int:
    try:
        from rapidfuzz import fuzz

        return int(fuzz.WRatio(a, b))
    except Exception:
        return 100 if a == b else (80 if a in b or b in a else 0)


def best_fuzzy_match(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    language: str = "ar",
    min_score: int = 45,
) -> tuple[dict[str, Any] | None, int, list[tuple[dict[str, Any], int]]]:
    """Return best candidate, score, and ranked top hits."""
    normalized = normalize_query(query, language)
    if not normalized:
        return None, 0, []

    ranked: list[tuple[dict[str, Any], int]] = []
    for candidate in candidates:
        haystacks = [
            str(candidate.get("name") or ""),
            str(candidate.get("name_ar") or ""),
            str(candidate.get("name_en") or ""),
            str(candidate.get("category") or ""),
            str(candidate.get("category_ar") or ""),
        ]
        best = 0
        for hay in haystacks:
            if not hay:
                continue
            best = max(best, fuzzy_score(normalized, normalize_query(hay, language)))
            for token in normalized.split():
                best = max(best, fuzzy_score(token, normalize_query(hay, language)))
        if best >= min_score:
            ranked.append((candidate, best))

    ranked.sort(key=lambda x: x[1], reverse=True)
    if not ranked:
        return None, 0, []
    best_item, best_score = ranked[0]
    return best_item, best_score, ranked


def normalize_ar_legacy(text: str) -> str:
    """Backward-compatible alias used by agent kb."""
    return normalize_ar(text)
