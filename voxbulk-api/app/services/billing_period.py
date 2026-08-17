"""Billing period ends in Europe/London calendar months / years."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def _as_london(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LONDON)


def add_billing_period(start: datetime, interval: str) -> datetime:
    """Return naive UTC datetime for the next monthly or yearly period end."""
    aware = _as_london(start)
    kind = str(interval or "monthly").strip().lower()
    if kind == "yearly":
        year = aware.year + 1
        day = min(aware.day, calendar.monthrange(year, aware.month)[1])
        nxt = aware.replace(year=year, day=day)
    else:
        month = aware.month + 1
        year = aware.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(aware.day, calendar.monthrange(year, month)[1])
        nxt = aware.replace(year=year, month=month, day=day)
    return nxt.astimezone(timezone.utc).replace(tzinfo=None)


def period_start_from_end(period_end: datetime, interval: str) -> datetime:
    """Approximate period start as one interval before period_end."""
    aware = _as_london(period_end)
    kind = str(interval or "monthly").strip().lower()
    if kind == "yearly":
        year = aware.year - 1
        day = min(aware.day, calendar.monthrange(year, aware.month)[1])
        prev = aware.replace(year=year, day=day)
    else:
        month = aware.month - 1
        year = aware.year
        if month < 1:
            month = 12
            year -= 1
        day = min(aware.day, calendar.monthrange(year, month)[1])
        prev = aware.replace(year=year, month=month, day=day)
    return prev.astimezone(timezone.utc).replace(tzinfo=None)
