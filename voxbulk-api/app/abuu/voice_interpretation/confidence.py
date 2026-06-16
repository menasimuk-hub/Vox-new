"""Combine STT, correction, intent, and menu-match signals into confidence tiers."""

from __future__ import annotations


def combined_intent_confidence(
    *,
    stt_confidence: float,
    correction_confidence: float,
    intent_confidence: float,
    menu_match_confidence: float,
) -> float:
    weights = (0.15, 0.25, 0.35, 0.25)
    parts = (stt_confidence, correction_confidence, intent_confidence, menu_match_confidence)
    return max(0.0, min(1.0, sum(w * p for w, p in zip(weights, parts))))


def should_proceed(combined: float, *, strong_threshold: float) -> bool:
    return combined >= strong_threshold


def should_clarify(combined: float, *, clarify_threshold: float, strong_threshold: float) -> bool:
    return clarify_threshold <= combined < strong_threshold


def menu_candidates_ambiguous(top_score: float, second_score: float, *, gap: float = 0.15) -> bool:
    if top_score <= 0 or second_score <= 0:
        return False
    return (top_score - second_score) < gap
