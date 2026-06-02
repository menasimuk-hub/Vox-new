from __future__ import annotations

import pytest
from datetime import datetime, timedelta, time, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.services.interview_booking_service import (
    BOOKING_HOURS_END,
    _filter_slots_to_calling_hours,
    _slot_starts,
    interview_slot_minutes,
)
from app.utils.ofcom import OfcomWindow

UK_TZ = ZoneInfo("Europe/London")


@pytest.fixture(autouse=True)
def ten_minute_slots(monkeypatch):
    """Slot grid tests assume 10-minute slots regardless of local .env."""
    monkeypatch.setenv("INTERVIEW_SLOT_MINUTES", "10")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_slot_starts_respects_window_end():
    sm = interview_slot_minutes()
    start = datetime(2026, 6, 15, 8, 0, 0)
    end = datetime(2026, 6, 15, 18, 0, 0)
    slots = _slot_starts(start, end)
    assert slots
    assert all(s.minute % sm == 0 for s in slots)
    assert slots[-1] + timedelta(minutes=sm) <= end


def test_slot_starts_aligns_from_odd_window_start():
    start = datetime(2026, 6, 15, 8, 7, 0)
    end = datetime(2026, 6, 15, 18, 0, 0)
    slots = _slot_starts(start, end)
    assert slots
    assert slots[0] == datetime(2026, 6, 15, 8, 10, 0)


def test_filter_slots_caps_at_1730_uk_winter(monkeypatch):
    """Naive datetimes are stored as UTC; last bookable slot ends at 17:30 UK."""
    sm = interview_slot_minutes()
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
    slot_end = uk + timedelta(minutes=sm)
    assert slot_end.time() <= time(*BOOKING_HOURS_END)


def test_filter_slots_skips_hour_cap_when_relaxed(monkeypatch):
    monkeypatch.setenv("INTERVIEW_RELAX_HOURS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    order = MagicMock()
    order.org_id = "org-1"
    db = MagicMock()
    evening = datetime(2026, 6, 15, 20, 0, 0)
    filtered = _filter_slots_to_calling_hours(db, order, [evening])
    assert filtered == [evening]
    get_settings.cache_clear()
