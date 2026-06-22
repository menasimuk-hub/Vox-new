"""Billable call duration — round up partial minutes (telecom-style)."""

from __future__ import annotations

import math


def billable_call_minutes(duration_seconds: int | None) -> int:
    """Any connected talk time rounds up; zero/unknown duration is not billed per minute."""
    if duration_seconds is None:
        return 0
    try:
        secs = int(duration_seconds)
    except (TypeError, ValueError):
        return 0
    if secs <= 0:
        return 0
    return max(1, int(math.ceil(secs / 60)))


def call_outcome_label(*, status: str | None, hangup_cause: str | None = None, voicemail: bool = False) -> str:
    """Human-readable call outcome for admin / billing audit."""
    if voicemail:
        return "Voicemail / answering machine"
    st = str(status or "").strip().lower()
    cause = str(hangup_cause or "").strip().lower()
    if st == "completed":
        return "Completed (AI survey)"
    if st in {"no_answer", "no answer"} or "no_answer" in cause or "timeout" in cause:
        return "No answer"
    if st == "busy" or "busy" in cause:
        return "Busy"
    if st == "opted_out":
        return "Opted out"
    if st == "calling":
        return "In progress"
    if st == "failed":
        return "Failed"
    if st == "cancelled":
        return "Cancelled"
    if cause:
        return cause.replace("_", " ").title()
    return st.title() if st else "Unknown"
