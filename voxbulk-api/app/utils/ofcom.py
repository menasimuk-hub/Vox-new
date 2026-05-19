from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


UK_TZ = ZoneInfo("Europe/London")


@dataclass(frozen=True)
class OfcomWindow:
    start: time
    end: time


DEFAULT_CALL_WINDOW = OfcomWindow(start=time(8, 0), end=time(21, 0))


def now_uk() -> datetime:
    """Return timezone-aware current time in the UK (Europe/London)."""
    return datetime.now(tz=UK_TZ)


def is_within_calling_window(dt: datetime, window: OfcomWindow = DEFAULT_CALL_WINDOW) -> bool:
    """
    Minimal utility for UK calling-time checks.

    TODO: Replace with Ofcom-compliant policy rules (weekends, consent, opt-outs, quiet hours, etc.).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UK_TZ)
    local = dt.astimezone(UK_TZ)
    t = local.time()
    return window.start <= t <= window.end
