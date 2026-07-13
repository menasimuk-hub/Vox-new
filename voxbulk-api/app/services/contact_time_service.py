"""Platform-wide contact time windows (OFCOM / outreach compliance)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.platform_contact_time_settings import PlatformContactTimeSettings
from app.utils.callback_timezone import timezone_from_phone
from app.utils.ofcom import DEFAULT_CALL_WINDOW, OfcomWindow

ContactChannel = Literal["calling", "wa_survey_start"]

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
VALID_TIMEZONES = frozenset(
    {
        "UTC",
        "Europe/London",
        "Europe/Berlin",
        "Europe/Madrid",
        "Europe/Paris",
        "Europe/Rome",
        "Europe/Dublin",
        "America/New_York",
        "America/Chicago",
        "America/Los_Angeles",
        "America/Toronto",
        "America/Sao_Paulo",
        "Asia/Kolkata",
        "Asia/Dubai",
        "Asia/Singapore",
        "Africa/Johannesburg",
        "Australia/Sydney",
    }
)

_TZ_LABELS: dict[str, str] = {
    "Europe/London": "UK time",
    "Australia/Sydney": "Sydney time",
    "America/New_York": "US Eastern time",
    "America/Chicago": "US Central time",
    "America/Los_Angeles": "US Pacific time",
    "America/Toronto": "Toronto time",
    "Asia/Dubai": "UAE time",
    "Asia/Singapore": "Singapore time",
    "Asia/Kolkata": "India time",
    "Africa/Johannesburg": "South Africa time",
}


@dataclass(frozen=True)
class ContactWindow:
    days: frozenset[int]
    start: time
    end: time
    fallback_tz: str


def _parse_days(csv: str) -> frozenset[int]:
    out: set[int] = set()
    for part in str(csv or "").split(","):
        part = part.strip()
        if part.isdigit():
            day = int(part)
            if 1 <= day <= 7:
                out.add(day)
    return frozenset(out) if out else frozenset({1, 2, 3, 4, 5})


def _parse_hhmm(value: str, default: time) -> time:
    raw = str(value or "").strip()
    if not raw or ":" not in raw:
        return default
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return default


def _is_uk_phone(phone: str | None) -> bool:
    tz = timezone_from_phone(phone)
    return tz == "Europe/London"


def _effective_window(window: ContactWindow, phone: str | None) -> OfcomWindow:
    start = window.start
    end = window.end
    if _is_uk_phone(phone):
        start = max(start, DEFAULT_CALL_WINDOW.start)
        end = min(end, DEFAULT_CALL_WINDOW.end)
        if start > end:
            start, end = DEFAULT_CALL_WINDOW.start, DEFAULT_CALL_WINDOW.end
    return OfcomWindow(start=start, end=end)


def _local_dt(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        return dt.astimezone(timezone.utc)


def _window_for_channel(row: PlatformContactTimeSettings, channel: ContactChannel) -> ContactWindow:
    if channel == "calling":
        return ContactWindow(
            days=_parse_days(row.calling_days),
            start=_parse_hhmm(row.calling_start, time(8, 0)),
            end=_parse_hhmm(row.calling_end, time(21, 0)),
            fallback_tz=str(row.calling_fallback_tz or "Europe/London").strip() or "Europe/London",
        )
    return ContactWindow(
        days=_parse_days(row.wa_days),
        start=_parse_hhmm(row.wa_start, time(9, 0)),
        end=_parse_hhmm(row.wa_end, time(20, 0)),
        fallback_tz=str(row.wa_fallback_tz or "Europe/London").strip() or "Europe/London",
    )


def get_settings_row(db: Session) -> PlatformContactTimeSettings:
    row = db.get(PlatformContactTimeSettings, "default")
    if row is None:
        row = PlatformContactTimeSettings(id="default", updated_at=datetime.utcnow())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _days_to_labels(days: frozenset[int]) -> list[str]:
    return [DAY_LABELS[d - 1] for d in sorted(days)]


def _labels_to_days(labels: list[str]) -> str:
    idx = {label: i + 1 for i, label in enumerate(DAY_LABELS)}
    days = sorted({idx[label] for label in labels if label in idx})
    return ",".join(str(d) for d in days) if days else "1,2,3,4,5"


def settings_out(row: PlatformContactTimeSettings) -> dict[str, Any]:
    call_days = _parse_days(row.calling_days)
    wa_days_set = _parse_days(row.wa_days)
    return {
        "calling": {
            "days": _days_to_labels(call_days),
            "start": row.calling_start,
            "end": row.calling_end,
            "fallback_tz": row.calling_fallback_tz,
        },
        "wa_survey": {
            "days": _days_to_labels(wa_days_set),
            "start": row.wa_start,
            "end": row.wa_end,
            "fallback_tz": row.wa_fallback_tz,
        },
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_window_payload(
    *,
    days: list[str] | None,
    start: str | None,
    end: str | None,
    fallback_tz: str | None,
) -> tuple[str, str, str, str]:
    day_labels = [str(d).strip() for d in (days or []) if str(d).strip()]
    if not day_labels:
        raise ValueError("Select at least one active day")
    days_csv = _labels_to_days(day_labels)
    start_t = _parse_hhmm(str(start or ""), time(0, 0))
    end_t = _parse_hhmm(str(end or ""), time(23, 59))
    if start_t >= end_t:
        raise ValueError("End time must be after start time")
    tz = str(fallback_tz or "Europe/London").strip()
    if tz not in VALID_TIMEZONES:
        raise ValueError(f"Unsupported timezone: {tz}")
    return days_csv, f"{start_t.hour:02d}:{start_t.minute:02d}", f"{end_t.hour:02d}:{end_t.minute:02d}", tz


def update_calling_settings(db: Session, payload: dict[str, Any]) -> PlatformContactTimeSettings:
    row = get_settings_row(db)
    days_csv, start, end, tz = _validate_window_payload(
        days=payload.get("days"),
        start=payload.get("start"),
        end=payload.get("end"),
        fallback_tz=payload.get("fallback_tz"),
    )
    row.calling_days = days_csv
    row.calling_start = start
    row.calling_end = end
    row.calling_fallback_tz = tz
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_wa_settings(db: Session, payload: dict[str, Any]) -> PlatformContactTimeSettings:
    row = get_settings_row(db)
    days_csv, start, end, tz = _validate_window_payload(
        days=payload.get("days"),
        start=payload.get("start"),
        end=payload.get("end"),
        fallback_tz=payload.get("fallback_tz"),
    )
    row.wa_days = days_csv
    row.wa_start = start
    row.wa_end = end
    row.wa_fallback_tz = tz
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_recipient_timezone(phone: str | None, *, channel: ContactChannel, db: Session | None = None) -> str:
    """Phone country prefix first; fallback timezone only when prefix is unknown."""
    row = get_settings_row(db) if db is not None else None
    window = _window_for_channel(row, channel) if row is not None else ContactWindow(
        days=frozenset({1, 2, 3, 4, 5}),
        start=time(8, 0),
        end=time(21, 0),
        fallback_tz="Europe/London",
    )
    from_phone = timezone_from_phone(phone)
    if from_phone:
        return from_phone
    return str(window.fallback_tz or "Europe/London").strip() or "Europe/London"


def _moment_allowed(local: datetime, window: ContactWindow, eff: OfcomWindow) -> bool:
    if local.isoweekday() not in window.days:
        return False
    t = local.time().replace(second=0, microsecond=0)
    return eff.start <= t <= eff.end


def contact_allowed(
    db: Session,
    channel: ContactChannel,
    phone: str | None,
    *,
    now_utc: datetime | None = None,
) -> tuple[bool, str | None]:
    row = get_settings_row(db)
    window = _window_for_channel(row, channel)
    tz_name = resolve_recipient_timezone(phone, channel=channel, db=db)
    now = now_utc or datetime.now(timezone.utc)
    local = _local_dt(now, tz_name)
    eff = _effective_window(window, phone)
    if _moment_allowed(local, window, eff):
        return True, None
    label = _TZ_LABELS.get(tz_name, tz_name)
    ch = "calling" if channel == "calling" else "WhatsApp survey"
    return False, f"Outside {ch} hours ({eff.start.strftime('%H:%M')}–{eff.end.strftime('%H:%M')} {label})"


def next_allowed_utc(
    db: Session,
    channel: ContactChannel,
    phone: str | None,
    *,
    now_utc: datetime | None = None,
) -> datetime:
    row = get_settings_row(db)
    window = _window_for_channel(row, channel)
    tz_name = resolve_recipient_timezone(phone, channel=channel, db=db)
    cursor = now_utc or datetime.now(timezone.utc)
    for _ in range(336):
        local = _local_dt(cursor, tz_name)
        eff = _effective_window(window, phone)
        if _moment_allowed(local, window, eff):
            return cursor.astimezone(timezone.utc).replace(tzinfo=None)
        cursor = cursor + timedelta(minutes=30)
    return (cursor + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)


def time_to_pct(hhmm: str) -> float:
    t = _parse_hhmm(hhmm, time(0, 0))
    return ((t.hour * 60 + t.minute) / 1440.0) * 100.0


def effective_window_for_preview(db: Session) -> dict[str, Any]:
    row = get_settings_row(db)
    call = _window_for_channel(row, "calling")
    wa = _window_for_channel(row, "wa_survey_start")
    return {
        "calling": {
            "start_pct": time_to_pct(f"{call.start.hour:02d}:{call.start.minute:02d}"),
            "end_pct": time_to_pct(f"{call.end.hour:02d}:{call.end.minute:02d}"),
            "width_pct": max(
                time_to_pct(f"{call.end.hour:02d}:{call.end.minute:02d}")
                - time_to_pct(f"{call.start.hour:02d}:{call.start.minute:02d}"),
                1.0,
            ),
        },
        "wa_survey": {
            "start_pct": time_to_pct(f"{wa.start.hour:02d}:{wa.start.minute:02d}"),
            "end_pct": time_to_pct(f"{wa.end.hour:02d}:{wa.end.minute:02d}"),
            "width_pct": max(
                time_to_pct(f"{wa.end.hour:02d}:{wa.end.minute:02d}")
                - time_to_pct(f"{wa.start.hour:02d}:{wa.start.minute:02d}"),
                1.0,
            ),
        },
    }


def _slot_allowed(
    slot_start: datetime,
    *,
    slot_minutes: int,
    window: ContactWindow,
    eff: OfcomWindow,
    tz_name: str,
) -> bool:
    local_start = _local_dt(slot_start.replace(tzinfo=timezone.utc) if slot_start.tzinfo is None else slot_start, tz_name)
    local_end = local_start + timedelta(minutes=slot_minutes)
    if local_start.isoweekday() not in window.days:
        return False
    return eff.start <= local_start.time() and local_end.time() <= eff.end


def slots_within_calling_window(
    db: Session,
    phone: str | None,
    slot_starts: list[datetime],
    *,
    slot_minutes: int = 4,
) -> list[datetime]:
    row = get_settings_row(db)
    window = _window_for_channel(row, "calling")
    tz_name = resolve_recipient_timezone(phone, channel="calling", db=db)
    eff = _effective_window(window, phone)
    return [
        slot
        for slot in slot_starts
        if _slot_allowed(slot, slot_minutes=slot_minutes, window=window, eff=eff, tz_name=tz_name)
    ]


def calling_hours_label(db: Session, phone: str | None) -> tuple[str, str, str]:
    row = get_settings_row(db)
    window = _window_for_channel(row, "calling")
    tz_name = resolve_recipient_timezone(phone, channel="calling", db=db)
    eff = _effective_window(window, phone)
    tz_label = _TZ_LABELS.get(tz_name, tz_name)
    hours = f"{eff.start.strftime('%H:%M')}–{eff.end.strftime('%H:%M')} {tz_label}"
    return hours, tz_name, tz_label


def full_settings_payload(db: Session) -> dict[str, Any]:
    row = get_settings_row(db)
    out = settings_out(row)
    out["dial_preview"] = effective_window_for_preview(db)
    out["timezones"] = sorted(VALID_TIMEZONES)
    return out
