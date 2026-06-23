"""Read busy times and sync appointment events to org calendar providers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config
from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_GRAPH_EVENTS = "https://graph.microsoft.com/v1.0/me/events"
MICROSOFT_GRAPH_CALENDAR_VIEW = "https://graph.microsoft.com/v1.0/me/calendarView"

CALENDAR_API_PROVIDERS = frozenset({"google_calendar", "microsoft_calendar"})


def _effective_start(appt: Appointment) -> datetime | None:
    target = appt.rescheduled_to_datetime or appt.appointment_datetime
    return target if isinstance(target, datetime) else None


def calendar_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_config(db, org_id)
    enabled = bool(cfg.get("calendar_enabled"))
    sched = get_scheduling_config(db, org_id)
    provider = str(sched.get("provider") or "").strip().lower()
    api_ready = enabled and provider in CALENDAR_API_PROVIDERS and bool(str(sched.get("access_token") or "").strip())
    return {
        "calendar_enabled": enabled,
        "provider": provider or None,
        "api_ready": api_ready,
        "slot_duration_minutes": int(cfg.get("slot_duration_minutes") or 30),
        "calendar_id": str(cfg.get("calendar_id") or "primary").strip() or "primary",
        "human_scheduling_ready": bool(provider) and bool(
            str(sched.get("schedule_url") or sched.get("meeting_link_url") or "").strip()
        ),
    }


def _persist_refreshed_token(db: Session, org_id: str, *, access_token: str, expires_in: int) -> None:
    if not access_token:
        return
    save_scheduling_config(
        db,
        org_id,
        {
            "access_token": access_token,
            "expires_at": (datetime.utcnow() + timedelta(seconds=max(expires_in, 60))).isoformat(),
        },
    )


def _google_platform_credentials(db: Session) -> tuple[str, str]:
    from app.services.google_calendar_booking_service import _google_calendar_platform_credentials

    client_id, client_secret, _redirect = _google_calendar_platform_credentials(db)
    return client_id, client_secret


def _microsoft_platform_credentials(db: Session) -> tuple[str, str]:
    from app.services.microsoft_calendar_service import _ms_platform_credentials

    client_id, client_secret, _redirect, _tenant = _ms_platform_credentials(db)
    return client_id, client_secret


def _token_expired(cfg: dict[str, Any]) -> bool:
    raw = str(cfg.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return False
    return expires <= datetime.utcnow() + timedelta(minutes=2)


def ensure_calendar_access_token(db: Session, org_id: str) -> tuple[str, str, dict[str, Any]]:
    sched = get_scheduling_config(db, org_id)
    provider = str(sched.get("provider") or "").strip().lower()
    if provider not in CALENDAR_API_PROVIDERS:
        raise ValueError("No calendar API provider connected — connect Google or Microsoft in Integrations")
    token = str(sched.get("access_token") or "").strip()
    refresh = str(sched.get("refresh_token") or "").strip()
    if token and not _token_expired(sched):
        return token, provider, sched
    if not refresh:
        raise ValueError("Calendar connection expired — reconnect in Settings → Integrations")

    if provider == "google_calendar":
        client_id, client_secret = _google_platform_credentials(db)
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh,
                },
            )
        if res.status_code >= 400:
            raise ValueError(f"Google Calendar token refresh failed: {res.text[:200]}")
        data = res.json() or {}
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise ValueError("Google Calendar token refresh returned no access token")
        _persist_refreshed_token(db, org_id, access_token=token, expires_in=int(data.get("expires_in") or 3600))
        return token, provider, get_scheduling_config(db, org_id)

    client_id, client_secret = _microsoft_platform_credentials(db)
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            MICROSOFT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "scope": "https://graph.microsoft.com/.default offline_access",
            },
        )
    if res.status_code >= 400:
        raise ValueError(f"Microsoft Calendar token refresh failed: {res.text[:200]}")
    data = res.json() or {}
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise ValueError("Microsoft Calendar token refresh returned no access token")
    _persist_refreshed_token(db, org_id, access_token=token, expires_in=int(data.get("expires_in") or 3600))
    return token, provider, get_scheduling_config(db, org_id)


def _iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _parse_busy_ranges_google(payload: dict[str, Any], calendar_id: str) -> list[tuple[datetime, datetime]]:
    calendars = payload.get("calendars") if isinstance(payload.get("calendars"), dict) else {}
    entry = calendars.get(calendar_id) if isinstance(calendars, dict) else {}
    busy = entry.get("busy") if isinstance(entry, dict) else []
    out: list[tuple[datetime, datetime]] = []
    for row in busy if isinstance(busy, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            start = datetime.fromisoformat(str(row.get("start") or "").replace("Z", "+00:00")).replace(tzinfo=None)
            end = datetime.fromisoformat(str(row.get("end") or "").replace("Z", "+00:00")).replace(tzinfo=None)
            if end > start:
                out.append((start, end))
        except ValueError:
            continue
    return out


def _parse_busy_ranges_microsoft(items: list[Any]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        try:
            start = datetime.fromisoformat(str(row.get("start", {}).get("dateTime") or "").replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            end = datetime.fromisoformat(str(row.get("end", {}).get("dateTime") or "").replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            if end > start:
                out.append((start, end))
        except (ValueError, AttributeError):
            continue
    return out


def get_busy_intervals(
    db: Session,
    org_id: str,
    *,
    from_dt: datetime,
    to_dt: datetime,
    calendar_id: str | None = None,
) -> list[tuple[datetime, datetime]]:
    cfg = get_config(db, org_id)
    if not cfg.get("calendar_enabled"):
        return []
    try:
        token, provider, _sched = ensure_calendar_access_token(db, org_id)
    except ValueError:
        return []

    cal_id = str(calendar_id or cfg.get("calendar_id") or "primary").strip() or "primary"
    headers = {"Authorization": f"Bearer {token}"}

    if provider == "google_calendar":
        body = {
            "timeMin": _iso_z(from_dt),
            "timeMax": _iso_z(to_dt),
            "items": [{"id": cal_id}],
        }
        with httpx.Client(timeout=30.0) as client:
            res = client.post(GOOGLE_FREEBUSY_URL, headers=headers, json=body)
        if res.status_code >= 400:
            logger.warning("google_freebusy_failed org=%s status=%s", org_id, res.status_code)
            return []
        return _parse_busy_ranges_google(res.json() or {}, cal_id)

    params = {
        "startDateTime": _iso_z(from_dt),
        "endDateTime": _iso_z(to_dt),
        "$select": "start,end",
        "$top": "250",
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            MICROSOFT_GRAPH_CALENDAR_VIEW,
            headers={**headers, "Prefer": 'outlook.timezone="UTC"'},
            params=params,
        )
    if res.status_code >= 400:
        logger.warning("microsoft_calendar_view_failed org=%s status=%s", org_id, res.status_code)
        return []
    items = (res.json() or {}).get("value") or []
    return _parse_busy_ranges_microsoft(items if isinstance(items, list) else [])


def _event_title(appt: Appointment) -> str:
    service = str(appt.service_type or "").strip()
    name = str(appt.contact_name or "Contact").strip()
    if service:
        return f"{service} — {name}"
    return f"Appointment — {name}"


def _event_body(appt: Appointment) -> str:
    parts = [f"Contact: {appt.contact_name}", f"Phone: {appt.contact_phone}"]
    if appt.contact_email:
        parts.append(f"Email: {appt.contact_email}")
    if appt.location:
        parts.append(f"Location: {appt.location}")
    if appt.branch:
        parts.append(f"Branch: {appt.branch}")
    parts.append("Managed by VoxBulk Appointment Manager")
    return "\n".join(parts)


def _create_google_event(
    token: str,
    *,
    calendar_id: str,
    appt: Appointment,
    start: datetime,
    duration_minutes: int,
) -> str:
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "summary": _event_title(appt),
        "description": _event_body(appt),
        "start": {"dateTime": start.isoformat(), "timeZone": appt.timezone or "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": appt.timezone or "UTC"},
    }
    if appt.contact_email:
        body["attendees"] = [{"email": appt.contact_email}]
    url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events"
    with httpx.Client(timeout=30.0) as client:
        res = client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if res.status_code >= 400:
        raise ValueError(f"Google Calendar event create failed: {res.text[:300]}")
    event_id = str((res.json() or {}).get("id") or "").strip()
    if not event_id:
        raise ValueError("Google Calendar did not return an event id")
    return event_id


def _update_google_event(
    token: str,
    *,
    calendar_id: str,
    event_id: str,
    appt: Appointment,
    start: datetime,
    duration_minutes: int,
) -> None:
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "summary": _event_title(appt),
        "description": _event_body(appt),
        "start": {"dateTime": start.isoformat(), "timeZone": appt.timezone or "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": appt.timezone or "UTC"},
    }
    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events/"
        f"{quote(event_id, safe='')}"
    )
    with httpx.Client(timeout=30.0) as client:
        res = client.patch(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if res.status_code >= 400:
        raise ValueError(f"Google Calendar event update failed: {res.text[:300]}")


def _delete_google_event(token: str, *, calendar_id: str, event_id: str) -> None:
    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events/"
        f"{quote(event_id, safe='')}"
    )
    with httpx.Client(timeout=30.0) as client:
        res = client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if res.status_code >= 400 and res.status_code != 404:
        raise ValueError(f"Google Calendar event delete failed: {res.text[:300]}")


def _create_microsoft_event(
    token: str,
    *,
    appt: Appointment,
    start: datetime,
    duration_minutes: int,
) -> str:
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "subject": _event_title(appt),
        "body": {"contentType": "Text", "content": _event_body(appt)},
        "start": {"dateTime": start.isoformat(), "timeZone": appt.timezone or "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": appt.timezone or "UTC"},
    }
    if appt.contact_email:
        body["attendees"] = [{"emailAddress": {"address": appt.contact_email}, "type": "required"}]
    with httpx.Client(timeout=30.0) as client:
        res = client.post(MICROSOFT_GRAPH_EVENTS, headers={"Authorization": f"Bearer {token}"}, json=body)
    if res.status_code >= 400:
        raise ValueError(f"Microsoft Calendar event create failed: {res.text[:300]}")
    event_id = str((res.json() or {}).get("id") or "").strip()
    if not event_id:
        raise ValueError("Microsoft Calendar did not return an event id")
    return event_id


def _update_microsoft_event(
    token: str,
    *,
    event_id: str,
    appt: Appointment,
    start: datetime,
    duration_minutes: int,
) -> None:
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "subject": _event_title(appt),
        "body": {"contentType": "Text", "content": _event_body(appt)},
        "start": {"dateTime": start.isoformat(), "timeZone": appt.timezone or "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": appt.timezone or "UTC"},
    }
    url = f"{MICROSOFT_GRAPH_EVENTS}/{quote(event_id, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        res = client.patch(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if res.status_code >= 400:
        raise ValueError(f"Microsoft Calendar event update failed: {res.text[:300]}")


def _delete_microsoft_event(token: str, *, event_id: str) -> None:
    url = f"{MICROSOFT_GRAPH_EVENTS}/{quote(event_id, safe='')}"
    with httpx.Client(timeout=30.0) as client:
        res = client.delete(url, headers={"Authorization": f"Bearer {token}"})
    if res.status_code >= 400 and res.status_code != 404:
        raise ValueError(f"Microsoft Calendar event delete failed: {res.text[:300]}")


def maybe_sync_appointment_calendar(db: Session, appt: Appointment, *, action: str = "upsert") -> dict[str, Any]:
    cfg = get_config(db, appt.org_id)
    if not cfg.get("calendar_enabled"):
        return {"skipped": True, "reason": "calendar_disabled"}

    clean_action = str(action or "upsert").strip().lower()
    if clean_action == "cancel" or str(appt.status or "").strip().lower() == "cancelled":
        event_id = str(appt.calendar_event_id or "").strip()
        if not event_id:
            return {"skipped": True, "reason": "no_event"}
        try:
            token, provider, _sched = ensure_calendar_access_token(db, appt.org_id)
            cal_id = str(cfg.get("calendar_id") or "primary").strip() or "primary"
            if provider == "google_calendar":
                _delete_google_event(token, calendar_id=cal_id, event_id=event_id)
            else:
                _delete_microsoft_event(token, event_id=event_id)
            appt.calendar_event_id = None
            append_log(db, appointment_id=appt.id, event_type="calendar_event_deleted", detail={"event_id": event_id})
            return {"ok": True, "action": "deleted"}
        except Exception as exc:
            logger.exception("appointment_calendar_delete_failed appointment_id=%s", appt.id)
            return {"ok": False, "error": str(exc)[:200]}

    start = _effective_start(appt)
    if start is None:
        return {"skipped": True, "reason": "no_datetime"}
    if str(appt.status or "").strip().lower() == "cancelled":
        return {"skipped": True, "reason": "cancelled"}

    duration = int(cfg.get("slot_duration_minutes") or 30)
    try:
        token, provider, _sched = ensure_calendar_access_token(db, appt.org_id)
    except ValueError as exc:
        return {"skipped": True, "reason": str(exc)}

    cal_id = str(cfg.get("calendar_id") or "primary").strip() or "primary"
    event_id = str(appt.calendar_event_id or "").strip()
    try:
        if event_id:
            if provider == "google_calendar":
                _update_google_event(token, calendar_id=cal_id, event_id=event_id, appt=appt, start=start, duration_minutes=duration)
            else:
                _update_microsoft_event(token, event_id=event_id, appt=appt, start=start, duration_minutes=duration)
            append_log(db, appointment_id=appt.id, event_type="calendar_event_updated", detail={"event_id": event_id})
            return {"ok": True, "action": "updated", "event_id": event_id}

        if provider == "google_calendar":
            new_id = _create_google_event(token, calendar_id=cal_id, appt=appt, start=start, duration_minutes=duration)
        else:
            new_id = _create_microsoft_event(token, appt=appt, start=start, duration_minutes=duration)
        appt.calendar_event_id = new_id
        append_log(db, appointment_id=appt.id, event_type="calendar_event_created", detail={"event_id": new_id})
        return {"ok": True, "action": "created", "event_id": new_id}
    except Exception as exc:
        logger.exception("appointment_calendar_sync_failed appointment_id=%s", appt.id)
        return {"ok": False, "error": str(exc)[:200]}
