from __future__ import annotations

from datetime import datetime

from app.services.interview_calendar_service import (
    build_interview_calendar_variables,
    build_interview_ics,
)


def test_build_interview_calendar_variables():
    start = datetime(2026, 6, 9, 10, 30, 0)
    vars = build_interview_calendar_variables(
        token="abc-123",
        slot_start=start,
        role="Engineer",
        company_name="Acme Ltd",
    )
    assert "calendar.google.com" in vars["calendar_google_url"]
    assert "outlook.live.com" in vars["calendar_outlook_url"]
    assert "/public/interview-booking/abc-123/calendar.ics" in vars["calendar_ics_url"]
    assert "Google Calendar" in vars["calendar_links_html"]
    assert "Outlook" in vars["calendar_links_html"]


def test_build_interview_ics_contains_event():
    start = datetime(2026, 6, 9, 10, 30, 0)
    end = datetime(2026, 6, 9, 11, 0, 0)
    ics = build_interview_ics(
        slot_start=start,
        slot_end=end,
        title="Engineer interview",
        description="Phone screening",
        uid="test@voxbulk.com",
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "Engineer interview" in ics
    assert "UID:test@voxbulk.com" in ics
