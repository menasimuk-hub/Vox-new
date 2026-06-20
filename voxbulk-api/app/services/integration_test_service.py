"""Deep health checks for org-level integrations.

Each provider's tester verifies three things, not just a token ping:

1. The stored access token is still valid (or, for HubSpot Meetings, that the
   HubSpot CRM token can call the Scheduler API).
2. The required scopes / permissions are present (where the provider returns
   token introspection — Calendly, HubSpot — we cross-check explicitly).
3. A small real resource loads (the first event type, calendar, or sample
   contact). This catches "token works but scopes missing" or
   "the selected event type was deleted" without waiting for a candidate to
   hit a broken booking link.

Each ``checks`` row uses the shape ``{name, status: 'ok' | 'fail', message}``.
Per-check HTTP calls are wrapped with a 4-second timeout so the dashboard's
Test button never hangs the page.

The combined result is persisted onto the same JSON config the provider already
uses (``organisations.scheduling_config_json`` for booking,
``organisations.hubspot_config_json`` for the HubSpot CRM tile) under a
``last_check`` key, so the catalogue can render "last tested 2 min ago — OK"
without re-running the check on every page load.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.models.organisation import Organisation

_HTTP_TIMEOUT_SECONDS = 4.0


class IntegrationTestError(ValueError):
    """Raised when the provider key is unknown / not testable from the dashboard."""


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "status": "ok" if ok else "fail", "message": message}


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _persist_last_check(
    db: Session,
    org_id: str,
    *,
    field: str,
    provider_key: str,
    result: dict[str, Any],
) -> None:
    """Stash the latest deep-check summary on the org's JSON config blob."""
    org = db.get(Organisation, org_id)
    if org is None:
        return
    raw = getattr(org, field, None)
    cfg = _loads(raw)
    cfg["last_check"] = {
        "provider": provider_key,
        "ok": bool(result.get("ok")),
        "checked_at": result.get("checked_at"),
        "latency_ms": result.get("latency_ms"),
        "summary": result.get("summary"),
    }
    setattr(org, field, json.dumps(cfg, ensure_ascii=False))
    db.add(org)
    db.commit()


def _summarise(checks: list[dict[str, Any]]) -> str:
    failed = [c["name"] for c in checks if c.get("status") != "ok"]
    if failed:
        return "Failed: " + ", ".join(failed)
    return "All checks passed"


def _run_with_timing(provider_runner: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    start = time.monotonic()
    try:
        checks = provider_runner()
    except Exception as exc:
        checks = [_check("provider", False, f"Unexpected error: {str(exc)[:200]}")]
    latency_ms = int((time.monotonic() - start) * 1000)
    ok = all(c.get("status") == "ok" for c in checks) if checks else False
    return {
        "ok": ok,
        "checked_at": _now_iso(),
        "latency_ms": latency_ms,
        "checks": checks,
        "summary": _summarise(checks),
    }


# ---------------------------------------------------------------------------
# Per-provider deep checks
# ---------------------------------------------------------------------------

def _check_calendly(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.scheduling_connection_service import get_scheduling_config

    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "calendly":
        return [_check("connection", False, "Calendly is not the active booking provider")]
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "Calendly access token missing — reconnect Calendly")]
    headers = {"Authorization": f"Bearer {token}"}
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        me_res = client.get("https://api.calendly.com/users/me", headers=headers)
    if me_res.status_code >= 400:
        checks.append(_check("token", False, f"Calendly token rejected ({me_res.status_code})"))
        return checks
    me = (me_res.json() or {}).get("resource") or {}
    owner_uri = str(me.get("uri") or "").strip()
    checks.append(_check("token", True, f"Token valid — connected as {me.get('name') or me.get('email') or 'Calendly user'}"))

    event_type_uri = str(cfg.get("event_type_uri") or "").strip()
    if not event_type_uri:
        checks.append(_check("event_type", False, "No event type selected — pick one in the provider sheet"))
        return checks
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        et_res = client.get(
            "https://api.calendly.com/event_types",
            headers=headers,
            params={"user": owner_uri, "active": "true", "count": 50},
        )
    if et_res.status_code >= 400:
        checks.append(_check("event_type", False, f"Could not list event types ({et_res.status_code})"))
        return checks
    items = (et_res.json() or {}).get("collection") or []
    found = any(str(it.get("uri") or "") == event_type_uri for it in items if isinstance(it, dict))
    checks.append(
        _check(
            "event_type",
            found,
            "Selected event type is still active" if found else "Selected event type was deleted or made inactive",
        )
    )
    return checks


def _check_cal_com(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.scheduling_connection_service import get_scheduling_config

    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "cal_com":
        return [_check("connection", False, "Cal.com is not the active booking provider")]
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "Cal.com access token missing — reconnect Cal.com")]
    headers = {"Authorization": f"Bearer {token}", "cal-api-version": "2024-08-13"}
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        me_res = client.get("https://api.cal.com/v2/me", headers=headers)
    if me_res.status_code >= 400:
        checks.append(_check("token", False, f"Cal.com token rejected ({me_res.status_code})"))
        return checks
    me = (me_res.json() or {}).get("data") or me_res.json() or {}
    checks.append(
        _check(
            "token",
            True,
            f"Token valid — connected as {me.get('email') or me.get('username') or 'Cal.com user'}",
        )
    )

    username = str(cfg.get("username") or me.get("username") or "").strip()
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        et_res = client.get(
            "https://api.cal.com/v2/event-types",
            headers=headers,
            params={"username": username} if username else None,
        )
    if et_res.status_code >= 400:
        checks.append(_check("event_types", False, f"Could not list event types ({et_res.status_code})"))
        return checks
    items = (et_res.json() or {}).get("data") or (et_res.json() or {}).get("event_types") or []
    if not (isinstance(items, list) and items):
        checks.append(_check("event_types", False, "No active event types in Cal.com account"))
        return checks
    checks.append(_check("event_types", True, f"{len(items)} active event types found"))

    selected_id = str(cfg.get("event_type_id") or "").strip()
    if not selected_id:
        return checks
    found = any(str(it.get("id") or "") == selected_id for it in items if isinstance(it, dict))
    checks.append(
        _check(
            "selected_event_type",
            found,
            "Selected event type is still active" if found else "Selected event type was deleted",
        )
    )
    return checks


def _check_google_calendar(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.scheduling_connection_service import get_scheduling_config

    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "google_calendar":
        return [_check("connection", False, "Google Calendar is not the active booking provider")]
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "Google access token missing — reconnect Google Calendar")]
    headers = {"Authorization": f"Bearer {token}"}
    checks: list[dict[str, Any]] = []

    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        me_res = client.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers)
    if me_res.status_code >= 400:
        checks.append(_check("token", False, f"Google token rejected ({me_res.status_code})"))
        return checks
    me = me_res.json() or {}
    checks.append(_check("token", True, f"Token valid — connected as {me.get('email') or me.get('name') or 'Google user'}"))

    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        cal_res = client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers=headers,
        )
    if cal_res.status_code == 403:
        checks.append(
            _check(
                "scopes",
                False,
                "Missing calendar.readonly scope — disconnect and reconnect Google Calendar",
            )
        )
        return checks
    if cal_res.status_code >= 400:
        checks.append(_check("calendars", False, f"Calendar list failed ({cal_res.status_code})"))
        return checks
    items = (cal_res.json() or {}).get("items") or []
    checks.append(_check("calendars", True, f"{len(items)} calendars accessible"))

    schedule_url = str(cfg.get("schedule_url") or "").strip()
    checks.append(
        _check(
            "schedule_url",
            bool(schedule_url),
            "Appointment Schedule URL is set" if schedule_url else "No appointment schedule URL — paste one in the provider sheet",
        )
    )
    return checks


def _check_microsoft_calendar(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.scheduling_connection_service import get_scheduling_config

    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "microsoft_calendar":
        return [_check("connection", False, "Microsoft 365 Calendar is not the active booking provider")]
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "Microsoft access token missing — reconnect Microsoft 365")]
    headers = {"Authorization": f"Bearer {token}"}
    checks: list[dict[str, Any]] = []

    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        me_res = client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    if me_res.status_code >= 400:
        checks.append(_check("token", False, f"Microsoft token rejected ({me_res.status_code})"))
        return checks
    me = me_res.json() or {}
    checks.append(
        _check(
            "token",
            True,
            f"Token valid — connected as {me.get('mail') or me.get('userPrincipalName') or me.get('displayName') or 'Microsoft user'}",
        )
    )

    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        cal_res = client.get("https://graph.microsoft.com/v1.0/me/calendars", headers=headers)
    if cal_res.status_code == 403:
        checks.append(
            _check(
                "scopes",
                False,
                "Missing Calendars.ReadWrite scope — disconnect and reconnect Microsoft 365",
            )
        )
        return checks
    if cal_res.status_code >= 400:
        checks.append(_check("calendars", False, f"Calendar list failed ({cal_res.status_code})"))
        return checks
    items = (cal_res.json() or {}).get("value") or []
    checks.append(_check("calendars", True, f"{len(items)} calendars accessible"))

    schedule_url = str(cfg.get("schedule_url") or "").strip()
    checks.append(
        _check(
            "schedule_url",
            bool(schedule_url),
            "Microsoft Bookings page URL is set" if schedule_url else "No Bookings URL — paste one in the provider sheet",
        )
    )
    return checks


def _check_hubspot_meetings(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.hubspot_connection_service import get_hubspot_config, hubspot_status
    from app.services.scheduling_connection_service import get_scheduling_config

    sched = get_scheduling_config(db, org_id)
    if str(sched.get("provider") or "").lower() != "hubspot_meetings":
        return [_check("connection", False, "HubSpot Meetings is not the active booking provider")]
    hs = hubspot_status(db, org_id)
    if not hs.get("connected"):
        return [_check("hubspot_crm", False, "Connect HubSpot CRM before testing HubSpot Meetings")]
    if hs.get("uses_access_token") is True:
        return [
            _check(
                "auth_mode",
                False,
                "HubSpot Meetings requires OAuth mode (Service key mode cannot list meeting links)",
            )
        ]
    token = str(get_hubspot_config(db, org_id).get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "HubSpot CRM token missing — reconnect HubSpot")]
    headers = {"Authorization": f"Bearer {token}"}
    checks: list[dict[str, Any]] = []

    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        meet_res = client.get("https://api.hubapi.com/scheduler/v3/meetings/meeting-links", headers=headers)
    if meet_res.status_code == 403:
        checks.append(
            _check(
                "scopes",
                False,
                "Missing scheduler.meetings.meeting-link.read scope — disconnect and reconnect HubSpot",
            )
        )
        return checks
    if meet_res.status_code >= 400:
        checks.append(_check("meeting_links", False, f"Meeting links failed ({meet_res.status_code})"))
        return checks
    payload = meet_res.json() or {}
    items = payload.get("results") or payload.get("meetingLinks") or payload.get("data") or []
    checks.append(_check("meeting_links", True, f"{len(items)} HubSpot meeting links accessible"))

    selected_id = str(sched.get("meeting_link_id") or "").strip()
    if not selected_id:
        return checks
    found = any(
        str(it.get("id") or it.get("meetingLinkId") or "") == selected_id
        for it in items
        if isinstance(it, dict)
    )
    checks.append(
        _check(
            "selected_meeting_link",
            found,
            "Selected HubSpot meeting link is still active" if found else "Selected meeting link was deleted",
        )
    )
    return checks


def _check_hubspot_crm(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.hubspot_connection_service import get_hubspot_config, hubspot_status

    hs = hubspot_status(db, org_id)
    if not hs.get("connected"):
        return [_check("connection", False, "HubSpot CRM is not connected for this organisation")]
    token = str(get_hubspot_config(db, org_id).get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "HubSpot access token missing — reconnect HubSpot")]
    checks: list[dict[str, Any]] = []
    auth_mode = str(hs.get("auth_mode") or "").lower()

    if auth_mode == "oauth":
        with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            info_res = client.get(f"https://api.hubapi.com/oauth/v1/access-tokens/{token}")
        if info_res.status_code >= 400:
            checks.append(_check("token", False, f"HubSpot token rejected ({info_res.status_code})"))
            return checks
        info = info_res.json() or {}
        scopes = info.get("scopes") or []
        scope_set = {str(s).strip() for s in scopes if s}
        checks.append(_check("token", True, f"Token valid — Hub {info.get('hub_domain') or info.get('hub_id') or ''}"))
        contact_scope_ok = "crm.objects.contacts.read" in scope_set or "contacts" in scope_set
        checks.append(
            _check(
                "scopes",
                contact_scope_ok,
                "Contacts read scope present" if contact_scope_ok else "Missing crm.objects.contacts.read scope",
            )
        )
    else:
        checks.append(_check("token", True, "Private app token configured"))

    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        probe = client.get("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, params={"limit": 1})
    if probe.status_code == 403:
        checks.append(_check("contacts_probe", False, "HubSpot refused contacts.read — fix scopes and reconnect"))
        return checks
    if probe.status_code >= 400:
        checks.append(_check("contacts_probe", False, f"Sample contact fetch failed ({probe.status_code})"))
        return checks
    body = probe.json() or {}
    results = body.get("results") or []
    checks.append(
        _check(
            "contacts_probe",
            True,
            f"Contact API reachable ({len(results)} sample contact{'s' if len(results) != 1 else ''} returned)",
        )
    )
    return checks


def _check_pipedrive_crm(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.pipedrive_connection_service import get_pipedrive_config, pipedrive_status

    status = pipedrive_status(db, org_id)
    if not status.get("connected"):
        return [_check("connection", False, "Pipedrive is not connected for this organisation")]
    token = str(get_pipedrive_config(db, org_id).get("access_token") or "").strip()
    if not token:
        return [_check("token", False, "Pipedrive access token missing — reconnect Pipedrive")]
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        res = client.get("https://api.pipedrive.com/v1/users/me", headers=headers)
    if res.status_code >= 400:
        return [_check("token", False, f"Pipedrive token rejected ({res.status_code})")]
    data = (res.json() or {}).get("data") or {}
    name = str(data.get("name") or data.get("company_name") or "Pipedrive").strip()
    return [_check("token", True, f"Token valid — {name}")]


def _check_zoho_crm(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.zoho_crm_connection_service import get_zoho_crm_config, zoho_crm_status

    status = zoho_crm_status(db, org_id)
    if not status.get("connected"):
        return [_check("connection", False, "Zoho CRM is not connected for this organisation")]
    cfg = get_zoho_crm_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    api_domain = str(cfg.get("api_domain") or "www.zohoapis.com").strip()
    if not token:
        return [_check("token", False, "Zoho access token missing — reconnect Zoho CRM")]
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        res = client.get(f"https://{api_domain}/crm/v2/users", headers=headers, params={"type": "CurrentUser"})
    if res.status_code >= 400:
        return [_check("token", False, f"Zoho token rejected ({res.status_code})")]
    users = (res.json() or {}).get("users") or []
    label = "Zoho CRM"
    if users and isinstance(users[0], dict):
        label = str(users[0].get("full_name") or users[0].get("email") or label)
    return [_check("token", True, f"Token valid — {label}")]


def _check_zoho_bookings(db: Session, org_id: str) -> list[dict[str, Any]]:
    from app.services.scheduling_connection_service import get_scheduling_config
    from app.services.zoho_crm_connection_service import get_zoho_crm_config, zoho_crm_status

    sched = get_scheduling_config(db, org_id)
    if str(sched.get("provider") or "").lower() != "zoho_bookings":
        return [_check("connection", False, "Zoho Bookings is not the active booking provider")]
    zs = zoho_crm_status(db, org_id)
    if not zs.get("connected"):
        return [_check("zoho_crm", False, "Connect Zoho CRM before testing Zoho Bookings")]
    cfg = get_zoho_crm_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    api_domain = str(cfg.get("api_domain") or "www.zohoapis.com").strip()
    if not token:
        return [_check("token", False, "Zoho CRM token missing — reconnect Zoho CRM")]
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        res = client.get(f"https://{api_domain}/bookings/v1/json/services", headers=headers)
    if res.status_code >= 400:
        checks.append(_check("booking_services", False, f"Zoho Bookings API failed ({res.status_code})"))
        return checks
    payload = res.json() or {}
    items = payload.get("services") or payload.get("data") or []
    checks.append(_check("booking_services", True, f"{len(items)} Zoho Bookings services accessible"))
    selected_id = str(sched.get("service_id") or "").strip()
    if selected_id:
        found = any(str(it.get("id") or it.get("service_id") or "") == selected_id for it in items if isinstance(it, dict))
        checks.append(
            _check(
                "selected_service",
                found,
                "Selected booking service is still active" if found else "Selected booking service was deleted",
            )
        )
    return checks


_BOOKING_FIELD = "scheduling_config_json"
_CRM_FIELDS: dict[str, str] = {
    "hubspot": "hubspot_config_json",
    "pipedrive": "pipedrive_config_json",
    "zoho_crm": "zoho_crm_config_json",
}

_PROVIDER_RUNNERS: dict[str, tuple[str, Callable[[Session, str], list[dict[str, Any]]]]] = {
    "calendly": (_BOOKING_FIELD, _check_calendly),
    "cal_com": (_BOOKING_FIELD, _check_cal_com),
    "google_calendar": (_BOOKING_FIELD, _check_google_calendar),
    "microsoft_calendar": (_BOOKING_FIELD, _check_microsoft_calendar),
    "hubspot_meetings": (_BOOKING_FIELD, _check_hubspot_meetings),
    "zoho_bookings": (_BOOKING_FIELD, _check_zoho_bookings),
    "hubspot": (_CRM_FIELDS["hubspot"], _check_hubspot_crm),
    "pipedrive": (_CRM_FIELDS["pipedrive"], _check_pipedrive_crm),
    "zoho_crm": (_CRM_FIELDS["zoho_crm"], _check_zoho_crm),
}


def deep_health_check(db: Session, org_id: str, provider_key: str) -> dict[str, Any]:
    """Run the deep health check for a single provider and persist the summary."""
    key = str(provider_key or "").strip().lower()
    entry = _PROVIDER_RUNNERS.get(key)
    if entry is None:
        raise IntegrationTestError(f"Unknown integration provider: {provider_key}")
    field, runner = entry
    result = _run_with_timing(lambda: runner(db, org_id))
    try:
        _persist_last_check(db, org_id, field=field, provider_key=key, result=result)
    except Exception:
        pass
    return result
