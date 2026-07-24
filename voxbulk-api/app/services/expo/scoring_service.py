"""Expo lead scoring — simple hot / warm / cold heuristic (no ML, no external calls)."""

from __future__ import annotations

_HOT_TIMELINE_HINTS = ("week", "asap", "immediate", "soon")
_WARM_TIMELINE_HINTS = ("month",)
_VAGUE_INTEREST_MAX_LEN = 7
_DETAILED_INTEREST_MIN_LEN = 20


def score_lead(*, interest: str | None, timeline: str | None, consent: bool) -> str:
    """Returns 'hot' | 'warm' | 'cold'.

    Rules (in order):
      - No consent, or a vague/empty interest answer -> cold
      - Timeline mentions week/asap/soon/immediate -> hot
      - Timeline mentions month -> warm
      - Otherwise: warm if the interest answer is reasonably detailed (>20 chars), else cold
    """
    interest_clean = str(interest or "").strip()
    timeline_clean = str(timeline or "").strip().lower()

    if not consent or len(interest_clean) <= _VAGUE_INTEREST_MAX_LEN:
        return "cold"

    if any(hint in timeline_clean for hint in _HOT_TIMELINE_HINTS):
        return "hot"

    if any(hint in timeline_clean for hint in _WARM_TIMELINE_HINTS):
        return "warm"

    return "warm" if len(interest_clean) > _DETAILED_INTEREST_MIN_LEN else "cold"
