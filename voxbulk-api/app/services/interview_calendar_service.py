"""Calendar links and ICS files for interview booking emails."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from app.services.brand_assets import api_public_origin
from app.services.interview_booking_service import SLOT_MINUTES


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _google_dates(start: datetime, end: datetime) -> str:
    s = _as_utc(start).strftime("%Y%m%dT%H%M%SZ")
    e = _as_utc(end).strftime("%Y%m%dT%H%M%SZ")
    return f"{s}/{e}"


def _iso_ics(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y%m%dT%H%M%SZ")


def build_interview_calendar_variables(
    *,
    token: str,
    slot_start: datetime,
    slot_end: datetime | None = None,
    role: str,
    company_name: str,
) -> dict[str, str]:
    """URLs and HTML snippet for add-to-calendar in interview emails."""
    from app.data.brand_email_layout import calendar_links_html

    end = slot_end or (slot_start + timedelta(minutes=SLOT_MINUTES))
    role_line = str(role or "Interview").strip() or "Interview"
    company_line = str(company_name or "VOXBULK").strip() or "VOXBULK"
    title = f"{role_line} interview — {company_line}"
    description = (
        f"AI phone interview for the {role_line} role at {company_line}. "
        "We will call you at the booked time on the number you provided."
    )
    location = "Phone call"

    safe_token = quote(str(token).strip(), safe="")
    ics_url = f"{api_public_origin().rstrip('/')}/public/interview-booking/{safe_token}/calendar.ics"

    google_url = (
        "https://calendar.google.com/calendar/render?"
        + urlencode(
            {
                "action": "TEMPLATE",
                "text": title,
                "dates": _google_dates(slot_start, end),
                "details": description,
                "location": location,
            }
        )
    )

    outlook_url = (
        "https://outlook.live.com/calendar/0/deeplink/compose?"
        + urlencode(
            {
                "subject": title,
                "body": description,
                "startdt": _as_utc(slot_start).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "enddt": _as_utc(end).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "location": location,
                "path": "/calendar/action/compose",
                "rru": "addevent",
            }
        )
    )

    links_html = calendar_links_html(
        google_url=google_url,
        outlook_url=outlook_url,
        ics_url=ics_url,
    )

    return {
        "calendar_google_url": google_url,
        "calendar_outlook_url": outlook_url,
        "calendar_ics_url": ics_url,
        "calendar_title": title,
        "calendar_links_html": links_html,
    }


def build_interview_ics(
    *,
    slot_start: datetime,
    slot_end: datetime,
    title: str,
    description: str,
    uid: str,
) -> str:
    """Minimal RFC 5545 calendar file for one interview slot."""
    now = datetime.now(timezone.utc)
    stamp = _iso_ics(now)
    start = _iso_ics(slot_start)
    end = _iso_ics(slot_end)
    safe_uid = str(uid or "interview@voxbulk.com").strip() or "interview@voxbulk.com"
    desc = str(description or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,")
    summary = str(title or "Interview").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,")

    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//VOXBULK//Interview Booking//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{safe_uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "LOCATION:Phone call",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
