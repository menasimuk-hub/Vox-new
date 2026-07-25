"""Org-level Google Appointment Schedule booking (paste URL — no Calendar API scopes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config


def test_google_calendar_platform_config(db: Session) -> dict[str, Any]:
    """Admin Test: Google Calendar booking is paste-URL only (no OAuth client required)."""
    from app.services.integration_release_service import IntegrationReleaseService
    from app.services.oauth_platform_test_service import finalize_platform_test
    from app.services.provider_settings import ProviderSettingsService

    summary = ProviderSettingsService.summary(db, provider="google_calendar")
    enabled = bool(summary.get("enabled"))
    release_ok = IntegrationReleaseService.provider_enabled(db, "google_calendar")
    checks = [
        {
            "name": "admin_enabled",
            "status": "ok" if enabled else "fail",
            "message": "Google Calendar is enabled in Admin" if enabled else "Enable Google Calendar in Admin → Integrations",
        },
        {
            "name": "release_mode",
            "status": "ok" if release_ok else "fail",
            "message": (
                "Visible to organisations (or Testing with testers)"
                if release_ok
                else "Provider is not released — set Testing or Live in Admin"
            ),
        },
    ]
    ok = enabled and release_ok
    return finalize_platform_test(
        checks,
        ok=ok,
        detail=(
            "Google Calendar booking is ready. Organisations paste an Appointment Schedule URL "
            "(no Google OAuth / Calendar scopes)."
            if ok
            else checks[-1]["message"] if not release_ok else checks[0]["message"]
        ),
        scopes="",
    )


def select_google_calendar_schedule(
    db: Session,
    org_id: str,
    *,
    schedule_url: str,
    schedule_name: str = "",
) -> dict[str, Any]:
    """Connect or update Google Calendar booking by pasting an Appointment Schedule URL."""
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    url = str(schedule_url or "").strip()
    if not url.startswith("http"):
        raise ValueError(
            "Paste your Google appointment schedule booking link "
            "(calendar.google.com/calendar/appointments/… or calendar.app.google/…)"
        )
    ensure_can_connect_scheduling(db, org_id, "google_calendar")
    name = str(schedule_name or "").strip() or "Google appointment schedule"
    # Full URL-only config — clear any legacy OAuth tokens so we never call Calendar APIs.
    return save_scheduling_config(
        db,
        org_id,
        {
            "provider": "google_calendar",
            "schedule_url": url,
            "schedule_name": name,
            "connection_mode": "url",
            "owner_name": "",
            "owner_email": "",
            "access_token": "",
            "refresh_token": "",
            "expires_at": "",
            "connected_at": datetime.utcnow().isoformat(),
            "_clear_oauth_tokens": True,
        },
    )


def create_google_calendar_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "google_calendar":
        raise ValueError("Google Calendar is not connected for this organisation")
    base_url = str(cfg.get("schedule_url") or "").strip()
    if not base_url:
        raise ValueError("Paste an appointment schedule URL in Settings → Integrations before sending links")
    params: dict[str, str] = {}
    email = str(candidate_email or "").strip()
    if email:
        params["email"] = email
    name = str(candidate_name or "").strip()
    if name:
        params["name"] = name
    if params:
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}{urlencode(params)}"
    return base_url
