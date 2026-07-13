from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.database import get_sessionmaker
from app.models.platform_contact_time_settings import PlatformContactTimeSettings
from app.services.contact_time_service import (
    contact_allowed,
    next_allowed_utc,
    resolve_recipient_timezone,
    slots_within_calling_window,
    update_calling_settings,
)


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture(autouse=True)
def platform_defaults(db):
    row = PlatformContactTimeSettings(
        id="default",
        calling_days="1,2,3,4,5",
        calling_start="08:00",
        calling_end="21:00",
        calling_fallback_tz="Europe/London",
        wa_days="1,2,3,4,5,6",
        wa_start="09:00",
        wa_end="20:00",
        wa_fallback_tz="Europe/London",
        updated_at=datetime.utcnow(),
    )
    db.merge(row)
    db.commit()
    return row


def test_contact_allowed_uk_inside_window(db):
    noon_uk = datetime(2026, 5, 20, 12, 0, tzinfo=ZoneInfo("Europe/London"))
    allowed, reason = contact_allowed(db, "calling", "+447954823445", now_utc=noon_uk)
    assert allowed is True
    assert reason is None


def test_contact_allowed_australia_outside_window(db):
    late_sydney = datetime(2026, 5, 20, 22, 30, tzinfo=ZoneInfo("Australia/Sydney"))
    allowed, reason = contact_allowed(db, "calling", "+61412345678", now_utc=late_sydney)
    assert allowed is False
    assert reason


def test_uk_floor_blocks_early_morning(db):
    update_calling_settings(
        db,
        {"days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "start": "06:00", "end": "22:00", "fallback_tz": "Europe/London"},
    )
    early = datetime(2026, 5, 20, 7, 0, tzinfo=ZoneInfo("Europe/London"))
    allowed, _ = contact_allowed(db, "calling", "+447954823445", now_utc=early)
    assert allowed is False


def test_wa_survey_start_separate_window(db):
    eight_uk = datetime(2026, 5, 20, 8, 30, tzinfo=ZoneInfo("Europe/London"))
    call_ok, _ = contact_allowed(db, "calling", "+447954823445", now_utc=eight_uk)
    wa_ok, _ = contact_allowed(db, "wa_survey_start", "+447954823445", now_utc=eight_uk)
    assert call_ok is True
    assert wa_ok is False


def test_unknown_prefix_uses_fallback(db):
    noon_utc = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    allowed, _ = contact_allowed(db, "calling", "+999123456", now_utc=noon_utc)
    assert allowed is True


def test_phone_prefix_beats_fallback_timezone(db):
    update_calling_settings(
        db,
        {
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "start": "08:00",
            "end": "21:00",
            "fallback_tz": "Australia/Sydney",
        },
    )
    assert resolve_recipient_timezone("+447954823445", channel="calling", db=db) == "Europe/London"
    assert resolve_recipient_timezone("+61412345678", channel="calling", db=db) == "Australia/Sydney"
    assert resolve_recipient_timezone("+999000", channel="calling", db=db) == "Australia/Sydney"


def test_slots_within_calling_window(db):
    slot = datetime(2026, 5, 20, 10, 0, 0)
    out = slots_within_calling_window(db, "+447954823445", [slot], slot_minutes=4)
    assert out == [slot]
    late = datetime(2026, 5, 20, 22, 0, 0)
    out_late = slots_within_calling_window(db, "+447954823445", [late], slot_minutes=4)
    assert out_late == []


def test_next_allowed_utc_defers(db):
    late = datetime(2026, 5, 20, 22, 0, tzinfo=ZoneInfo("Europe/London"))
    nxt = next_allowed_utc(db, "calling", "+447954823445", now_utc=late)
    assert isinstance(nxt, datetime)
    assert nxt > late.replace(tzinfo=None)

