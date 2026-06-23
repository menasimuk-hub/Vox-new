"""Org-level Google Calendar appointment schedule booking."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)


def _google_calendar_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="google_calendar")
            if enabled:
                cid = str(cfg.get("client_id") or "").strip()
                secret = str(cfg.get("client_secret") or "").strip()
                redirect = str(cfg.get("redirect_uri") or "").strip()
                if cid and secret and redirect:
                    return cid, secret, redirect
        except Exception:
            pass
    settings = get_settings()
    return (
        str(getattr(settings, "google_calendar_client_id", None) or "").strip(),
        str(getattr(settings, "google_calendar_client_secret", None) or "").strip(),
        str(getattr(settings, "google_calendar_redirect_uri", None) or "").strip(),
    )


def test_google_calendar_platform_config(db: Session) -> dict[str, Any]:
    from app.services.oauth_platform_test_service import (
        finalize_platform_test,
        mask_client_id,
        platform_credential_source,
        probe_confidential_oauth_token,
        validate_oauth_platform_fields,
    )

    client_id, client_secret, redirect = _google_calendar_platform_credentials(db)
    source = platform_credential_source(db, provider="google_calendar")
    checks, fields_ok = validate_oauth_platform_fields(
        client_id=client_id,
        client_secret=client_secret,
        redirect=redirect,
        provider_label="Google Calendar",
    )
    if not fields_ok:
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=GOOGLE_CALENDAR_SCOPES,
        )

    checks.append(
        {
            "name": "credential_source",
            "status": "ok" if source == "admin_db" else "fail",
            "message": (
                "Using Admin-saved credentials"
                if source == "admin_db"
                else "Using GOOGLE_CALENDAR_* env fallback — enable and save in Admin, or update .env"
            ),
        }
    )

    probe = probe_confidential_oauth_token(
        token_url=GOOGLE_TOKEN_URL,
        payload={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": "voxbulk-platform-test-invalid-code",
            "redirect_uri": redirect,
        },
        use_json=False,
    )
    if probe["reason"] == "client_not_found":
        checks.append({"name": "google_api", "status": "fail", "message": "Google rejected the OAuth client ID"})
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            redirect_uri=redirect,
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=GOOGLE_CALENDAR_SCOPES,
        )
    if probe["reason"] == "invalid_secret":
        checks.append(
            {"name": "google_api", "status": "fail", "message": "Google recognized client ID but rejected the secret"}
        )
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            redirect_uri=redirect,
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=GOOGLE_CALENDAR_SCOPES,
        )

    checks.append({"name": "google_api", "status": "ok", "message": probe["detail"]})
    return finalize_platform_test(
        checks,
        ok=True,
        detail="Google Calendar OAuth app verified. Connect from Dashboard → Integrations.",
        redirect_uri=redirect,
        credential_source=source,
        client_id_masked=mask_client_id(client_id),
        scopes=GOOGLE_CALENDAR_SCOPES,
    )


def google_calendar_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    ensure_can_connect_scheduling(db, org_id, "google_calendar", replace=replace)
    client_id, _, redirect = _google_calendar_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Google Calendar OAuth is not configured (Admin → Integrations → Google Calendar)")
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": GOOGLE_CALENDAR_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def google_calendar_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _google_calendar_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Google token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Google did not return an access token")

    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        me_res = client.get(GOOGLE_USERINFO_URL, headers=headers)
    if me_res.status_code >= 400:
        raise ValueError(f"Google user lookup failed: {me_res.text[:300]}")
    me = me_res.json() or {}
    owner_name = str(me.get("name") or "").strip()
    owner_email = str(me.get("email") or "").strip()

    schedule_url = ""
    schedule_name = ""
    schedules = list_google_calendar_schedules_with_token(access_token)
    if schedules:
        schedule_url = str(schedules[0].get("url") or "")
        schedule_name = str(schedules[0].get("name") or "")

    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "provider": "google_calendar",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "owner_name": owner_name,
        "owner_email": owner_email,
        "schedule_url": schedule_url,
        "schedule_name": schedule_name,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def list_google_calendar_schedules_with_token(access_token: str) -> list[dict[str, Any]]:
    """Best-effort list of bookable calendar resources; falls back to empty if API unavailable."""
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        cal_res = client.get("https://www.googleapis.com/calendar/v3/users/me/calendarList", headers=headers)
    if cal_res.status_code >= 400:
        return out
    for row in cal_res.json().get("items") or []:
        if not isinstance(row, dict):
            continue
        summary = str(row.get("summary") or "").strip()
        cal_id = str(row.get("id") or "").strip()
        if summary and cal_id:
            out.append({"id": cal_id, "name": summary, "url": ""})
    return out


def list_google_calendar_schedules(db: Session, org_id: str) -> list[dict[str, Any]]:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "google_calendar":
        raise ValueError("Google Calendar is not connected")
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        raise ValueError("Google Calendar connection is incomplete")
    rows = list_google_calendar_schedules_with_token(token)
    current_url = str(cfg.get("schedule_url") or "").strip()
    current_name = str(cfg.get("schedule_name") or "").strip()
    if current_url and not any(str(r.get("url") or "") == current_url for r in rows):
        rows.insert(0, {"id": "current", "name": current_name or "Current schedule", "url": current_url})
    return rows


def select_google_calendar_schedule(db: Session, org_id: str, *, schedule_url: str, schedule_name: str = "") -> dict[str, Any]:
    url = str(schedule_url or "").strip()
    if not url.startswith("http"):
        raise ValueError("A valid appointment schedule URL is required")
    cfg = dict(get_scheduling_config(db, org_id))
    if str(cfg.get("provider") or "").lower() != "google_calendar":
        raise ValueError("Google Calendar is not connected")
    cfg["schedule_url"] = url
    cfg["schedule_name"] = str(schedule_name or "").strip() or cfg.get("schedule_name") or "Appointment schedule"
    return save_scheduling_config(db, org_id, cfg)


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
        raise ValueError("Pick an appointment schedule in Settings → Integrations before sending links")
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
