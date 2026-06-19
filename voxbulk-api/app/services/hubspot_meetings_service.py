"""HubSpot Meetings booking via existing CRM OAuth token."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.services.hubspot_connection_service import get_hubspot_config, hubspot_status
from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config

HUBSPOT_MEETING_LINKS_URL = "https://api.hubapi.com/scheduler/v3/meetings/meeting-links"


def _hubspot_access_token(db: Session, org_id: str) -> str:
    hs = hubspot_status(db, org_id)
    if not hs.get("connected"):
        raise ValueError("Connect HubSpot CRM in Settings → Integrations before using HubSpot Meetings")
    if hs.get("uses_access_token") is True:
        raise ValueError("HubSpot Meetings requires OAuth HubSpot CRM (Service key mode cannot list meeting links)")
    token = str(get_hubspot_config(db, org_id).get("access_token") or "").strip()
    if not token:
        raise ValueError("HubSpot CRM token missing — reconnect HubSpot")
    return token


def list_hubspot_meeting_links(db: Session, org_id: str) -> list[dict[str, Any]]:
    token = _hubspot_access_token(db, org_id)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(HUBSPOT_MEETING_LINKS_URL, headers=headers)
    if res.status_code >= 400:
        raise ValueError(
            f"HubSpot meeting links failed ({res.status_code}). "
            "Ask your admin to add Scheduler scopes to the HubSpot app, then disconnect and reconnect CRM."
        )
    payload = res.json() or {}
    items = payload.get("results") or payload.get("meetingLinks") or payload.get("data") or []
    out: list[dict[str, Any]] = []
    for row in items if isinstance(items, list) else []:
        if not isinstance(row, dict):
            continue
        link_id = str(row.get("id") or row.get("meetingLinkId") or "").strip()
        name = str(row.get("name") or row.get("slug") or link_id or "Meeting link").strip()
        url = str(
            row.get("url")
            or row.get("link")
            or row.get("bookingUrl")
            or row.get("fullUrl")
            or ""
        ).strip()
        if link_id or url:
            out.append({"id": link_id, "name": name, "url": url})
    return out


def connect_hubspot_meetings(
    db: Session,
    org_id: str,
    *,
    meeting_link_id: str,
    meeting_link_url: str = "",
    meeting_link_name: str = "",
) -> dict[str, Any]:
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    ensure_can_connect_scheduling(db, org_id, "hubspot_meetings")
    wanted_id = str(meeting_link_id or "").strip()
    if not wanted_id:
        raise ValueError("meeting_link_id is required")

    url = str(meeting_link_url or "").strip()
    name = str(meeting_link_name or "").strip()
    if not url:
        for row in list_hubspot_meeting_links(db, org_id):
            if str(row.get("id") or "") == wanted_id:
                url = str(row.get("url") or "").strip()
                name = name or str(row.get("name") or "")
                break
    if not url:
        raise ValueError("Meeting link URL not found — pick a link from the list")

    hs = hubspot_status(db, org_id)
    cfg = {
        "provider": "hubspot_meetings",
        "meeting_link_id": wanted_id,
        "meeting_link_url": url,
        "meeting_link_name": name or "HubSpot meeting",
        "owner_name": str(hs.get("account_name") or "").strip(),
        "connected_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def create_hubspot_meetings_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "hubspot_meetings":
        raise ValueError("HubSpot Meetings is not connected for this organisation")
    base_url = str(cfg.get("meeting_link_url") or "").strip()
    if not base_url:
        raise ValueError("HubSpot meeting link missing — reconnect in Settings → Integrations")

    hs = hubspot_status(db, org_id)
    if not hs.get("connected"):
        raise ValueError("HubSpot CRM disconnected — reconnect CRM or switch booking provider")

    params: dict[str, str] = {}
    email = str(candidate_email or "").strip()
    if email:
        params["email"] = email
    first = str(candidate_name or "").strip().split()[0] if candidate_name else ""
    if first:
        params["firstname"] = first
    if params:
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{urlencode(params)}"
    return base_url
