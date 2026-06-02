from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.services.interview_booking_service import (
    BOOKING_HOURS_END,
    SLOT_MINUTES,
    _filter_slots_to_calling_hours,
    _slot_starts,
)
from app.utils.ofcom import OfcomWindow

UK_TZ = ZoneInfo("Europe/London")


def test_slot_starts_respects_window_end():
    start = datetime(2026, 6, 15, 8, 0, 0)
    end = datetime(2026, 6, 15, 18, 0, 0)
    slots = _slot_starts(start, end)
    assert slots
    assert slots[-1] + timedelta(minutes=SLOT_MINUTES) <= end


def test_filter_slots_caps_at_1730_uk_winter(monkeypatch):
    """Naive datetimes are stored as UTC; last bookable slot ends at 17:30 UK."""
    order = MagicMock()
    order.org_id = "org-1"
    db = MagicMock()

    monkeypatch.setattr(
        "app.utils.ofcom.resolve_org_call_window",
        lambda _db, _org_id, now=None: OfcomWindow(start=time(9, 0), end=time(18, 0)),
    )
    monkeypatch.setattr(
        "app.utils.ofcom.is_weekend_uk",
        lambda _dt: False,
    )

    window_start = datetime(2026, 1, 15, 8, 0, 0)
    window_end = datetime(2026, 1, 15, 20, 0, 0)
    raw = _slot_starts(window_start, window_end)
    filtered = _filter_slots_to_calling_hours(db, order, raw)

    assert filtered
    last = filtered[-1]
    uk = last.replace(tzinfo=timezone.utc).astimezone(UK_TZ)
    slot_end = uk + timedelta(minutes=SLOT_MINUTES)
    assert slot_end.time() <= time(*BOOKING_HOURS_END)
