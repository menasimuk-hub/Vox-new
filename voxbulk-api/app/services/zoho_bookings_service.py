"""Zoho Bookings — paste URL (standalone) or list services via Zoho CRM OAuth."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config
from app.services.zoho_crm_connection_service import _ensure_access_token, zoho_crm_status


def _zoho_access(db: Session, org_id: str) -> tuple[str, str]:
    hs = zoho_crm_status(db, org_id)
    if not hs.get("connected"):
        raise ValueError("Connect Zoho CRM to list booking services, or paste a Bookings URL instead")
    return _ensure_access_token(db, org_id)


def list_zoho_booking_services(db: Session, org_id: str) -> list[dict[str, Any]]:
    token, api_domain = _zoho_access(db, org_id)
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(f"https://{api_domain}/bookings/v1/json/services", headers=headers)
    if res.status_code >= 400:
        raise ValueError(
            f"Zoho Bookings services failed ({res.status_code}). "
            "Ensure Zoho Bookings scopes are granted, then disconnect and reconnect Zoho CRM."
        )
    payload = res.json() or {}
    items = payload.get("services") or payload.get("data") or payload.get("response", {}).get("returnvalue") or []
    out: list[dict[str, Any]] = []
    for row in items if isinstance(items, list) else []:
        if not isinstance(row, dict):
            continue
        service_id = str(row.get("id") or row.get("service_id") or "").strip()
        name = str(row.get("name") or row.get("service_name") or service_id or "Booking service").strip()
        url = str(row.get("booking_url") or row.get("url") or row.get("link") or "").strip()
        if service_id or url:
            out.append({"id": service_id, "name": name, "url": url})
    return out


def connect_zoho_bookings(
    db: Session,
    org_id: str,
    *,
    service_id: str = "",
    service_url: str = "",
    service_name: str = "",
) -> dict[str, Any]:
    """Connect Zoho Bookings by pasted URL, or by CRM-listed service id."""
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    ensure_can_connect_scheduling(db, org_id, "zoho_bookings")
    wanted_id = str(service_id or "").strip()
    url = str(service_url or "").strip()
    name = str(service_name or "").strip()

    if url.startswith("http") and not wanted_id:
        cfg = {
            "provider": "zoho_bookings",
            "service_id": "",
            "service_url": url,
            "service_name": name or "Zoho Bookings",
            "connection_mode": "url",
            "owner_name": "",
            "connected_at": datetime.utcnow().isoformat(),
        }
        return save_scheduling_config(db, org_id, cfg)

    if not wanted_id and not url.startswith("http"):
        raise ValueError("Paste a Zoho Bookings URL (https://…) or pick a service from Zoho CRM")

    if not url and wanted_id:
        for row in list_zoho_booking_services(db, org_id):
            if str(row.get("id") or "") == wanted_id:
                url = str(row.get("url") or "").strip()
                name = name or str(row.get("name") or "")
                break
    if not url.startswith("http"):
        raise ValueError("Booking service URL not found — paste a URL or pick a service from the list")

    zoho = zoho_crm_status(db, org_id)
    cfg = {
        "provider": "zoho_bookings",
        "service_id": wanted_id,
        "service_url": url,
        "service_name": name or "Zoho Bookings",
        "connection_mode": "crm_list" if wanted_id else "url",
        "owner_name": str(zoho.get("account_name") or "").strip(),
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def create_zoho_bookings_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "zoho_bookings":
        raise ValueError("Zoho Bookings is not connected for this organisation")
    base_url = str(cfg.get("service_url") or "").strip()
    if not base_url:
        raise ValueError("Zoho Bookings URL missing — paste a URL in Settings → Integrations")

    params: dict[str, str] = {}
    email = str(candidate_email or "").strip()
    if email:
        params["email"] = email
    first = str(candidate_name or "").strip().split()[0] if candidate_name else ""
    if first:
        params["name"] = first
    if params:
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{urlencode(params)}"
    return base_url
