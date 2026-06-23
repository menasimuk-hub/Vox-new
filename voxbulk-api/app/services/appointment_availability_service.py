"""Find free appointment slots from org hours, calendar busy times, and existing bookings."""
from __future__ import annotations
from datetime import datetime, time, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.appointment import Appointment
from app.services.appointment_calendar_service import get_busy_intervals
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config

def _parse_hhmm(raw, default):
    clean = str(raw or "").strip()
    if not clean or ":" not in clean:
        return default
    try:
        hour, minute = clean.split(":", 1)
        return time(int(hour), int(minute))
    except ValueError:
        return default

def _slot_conflicts(slot_start, duration_minutes, appt):
    start = appt.appointment_datetime
    if not isinstance(start, datetime):
        return False
    slot_end = slot_start + timedelta(minutes=duration_minutes)
    appt_end = start + timedelta(minutes=30)
    return slot_start < appt_end and slot_end > start

def _interval_conflicts(slot_start, duration_minutes, busy_start, busy_end):
    slot_end = slot_start + timedelta(minutes=duration_minutes)
    return slot_start < busy_end and slot_end > busy_start

def find_free_slots(db, org_id, *, from_dt=None, days=14, duration_minutes=None, limit=5, exclude_appointment_id=None):
    cfg = get_config(db, org_id)
    window_start = _parse_hhmm(cfg.get("outreach_window_start"), time(9, 0))
    window_end = _parse_hhmm(cfg.get("outreach_window_end"), time(16, 0))
    duration = int(duration_minutes or cfg.get("slot_duration_minutes") or 30)
    now = from_dt or datetime.utcnow()
    busy_rows = list(db.execute(select(Appointment).where(
        Appointment.org_id == org_id,
        Appointment.status.in_(("scheduled", "confirmed", "rescheduled")),
        Appointment.appointment_datetime >= now.replace(hour=0, minute=0, second=0, microsecond=0),
    )).scalars())
    if exclude_appointment_id:
        busy_rows = [row for row in busy_rows if row.id != exclude_appointment_id]

    calendar_busy: list[tuple[datetime, datetime]] = []
    if cfg.get("calendar_enabled"):
        range_end = now + timedelta(days=max(days, 1))
        calendar_busy = get_busy_intervals(db, org_id, from_dt=now, to_dt=range_end)

    slots = []
    day_base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(max(days, 1)):
        day = day_base + timedelta(days=offset)
        cursor = datetime.combine(day.date(), window_start)
        end = datetime.combine(day.date(), window_end)
        while cursor + timedelta(minutes=duration) <= end:
            if cursor > now and not any(_slot_conflicts(cursor, duration, row) for row in busy_rows):
                if not any(_interval_conflicts(cursor, duration, b0, b1) for b0, b1 in calendar_busy):
                    slots.append(cursor)
                    if len(slots) >= limit:
                        return slots
            cursor += timedelta(minutes=duration)
    return slots

def auto_assign_reschedule_slot(db, appt):
    if appt.rescheduled_to_datetime is not None:
        return appt.rescheduled_to_datetime
    slots = find_free_slots(db, appt.org_id, exclude_appointment_id=appt.id, limit=1)
    if not slots:
        append_log(db, appointment_id=appt.id, event_type="reschedule_no_slots", detail={})
        return None
    chosen = slots[0]
    appt.rescheduled_to_datetime = chosen
    appt.status = "rescheduled"
    append_log(db, appointment_id=appt.id, event_type="reschedule_auto_assigned", detail={"slot": chosen.isoformat()})
    return chosen
