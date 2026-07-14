from __future__ import annotations

import pytest
from datetime import datetime, timedelta, time, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.services.interview_booking_service import (
    MEETING_CHANNEL,
    PHONE_CHANNEL,
    _filter_slots_to_calling_hours,
    _slot_starts,
    interview_slot_minutes,
    resolve_booking_channel_options,
)

UK_TZ = ZoneInfo("Europe/London")


@pytest.fixture()
def db():
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as session:
        yield session


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


def test_filter_slots_caps_at_calling_window(db):
    """Slots outside platform calling hours are removed for UK numbers."""
    sm = interview_slot_minutes()
    from app.models.platform_contact_time_settings import PlatformContactTimeSettings

    row = db.get(PlatformContactTimeSettings, "default")
    if row is None:
        row = PlatformContactTimeSettings(id="default", updated_at=datetime.utcnow())
        db.add(row)
    row.calling_days = "1,2,3,4,5"
    row.calling_start = "09:00"
    row.calling_end = "17:30"
    row.calling_fallback_tz = "Europe/London"
    db.commit()

    window_start = datetime(2026, 1, 15, 8, 0, 0)
    window_end = datetime(2026, 1, 15, 20, 0, 0)
    raw = _slot_starts(window_start, window_end)
    filtered = _filter_slots_to_calling_hours(db, "+447954823445", raw)

    assert filtered
    last = filtered[-1]
    uk = last.replace(tzinfo=timezone.utc).astimezone(UK_TZ)
    slot_end = uk + timedelta(minutes=sm)
    assert slot_end.time() <= time(17, 30)


def test_booking_window_extends_to_24h_when_relaxed(monkeypatch):
    monkeypatch.setenv("INTERVIEW_RELAX_HOURS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    order = MagicMock()
    start = datetime(2026, 6, 15, 8, 0, 0)
    order.scheduled_start_at = start
    order.scheduled_end_at = start + timedelta(hours=6)
    win_start, win_end = __import__(
        "app.services.interview_booking_service", fromlist=["booking_window_bounds"]
    ).booking_window_bounds(order)
    assert win_start == start
    assert win_end == start + timedelta(hours=24)
    get_settings.cache_clear()


def test_filter_slots_skips_hour_cap_when_relaxed(monkeypatch):
    monkeypatch.setenv("INTERVIEW_RELAX_HOURS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    db = MagicMock()
    evening = datetime(2026, 6, 15, 20, 0, 0)
    filtered = _filter_slots_to_calling_hours(db, "+447954823445", [evening])
    assert filtered == [evening]
    get_settings.cache_clear()


def test_resolve_booking_channel_meeting_only_when_call_allowlist_blocks(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.telnyx_phone_allowlist_service.TelnyxPhoneAllowlistService.validate_phone_db",
        lambda *a, **k: {"allowed": False, "reason": "EG calling is disabled"},
    )
    opts = resolve_booking_channel_options(db, "+201012345678")
    assert opts["phone_available"] is False
    assert opts["meeting_available"] is True
    assert opts["default_channel"] == MEETING_CHANNEL


def test_resolve_booking_channel_phone_when_call_allowlist_allows(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.telnyx_phone_allowlist_service.TelnyxPhoneAllowlistService.validate_phone_db",
        lambda *a, **k: {"allowed": True},
    )
    opts = resolve_booking_channel_options(db, "+447700900123")
    assert opts["phone_available"] is True
    assert opts["meeting_available"] is True
    assert opts["default_channel"] == PHONE_CHANNEL
