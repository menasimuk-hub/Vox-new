"""Org-level Microsoft 365 / Outlook Calendar booking provider.

Mirrors the Google Calendar pattern (OAuth start, callback, schedule URL paste,
disconnect) so the redesigned Integrations page can treat all five booking
providers uniformly.

Microsoft Entra is registered as a multi-tenant app — any customer's Microsoft
365 tenant can authorise — so the authority URL is ``/common``. Scopes follow
Microsoft Graph defaults (`User.Read` + `Calendars.ReadWrite` + the standard
OIDC trio). The customer pastes their Microsoft Bookings public page URL (or any
publicly bookable Outlook page URL) which we append candidate query params to,
exactly like Google.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.scheduling_connection_service import get_scheduling_config, save_scheduling_config

MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_GRAPH_ME = "https://graph.microsoft.com/v1.0/me"
MICROSOFT_GRAPH_CALENDARS = "https://graph.microsoft.com/v1.0/me/calendars"
MICROSOFT_SCOPES = (
    "openid profile email offline_access "
    "User.Read Calendars.ReadWrite"
)


def _ms_platform_credentials(db: Session | None = None) -> tuple[str, str, str, str]:
    """Return ``(client_id, client_secret, redirect_uri, tenant)`` from admin config."""
    tenant = "common"
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="microsoft_calendar")
            if enabled and isinstance(cfg, dict):
                cid = str(cfg.get("client_id") or "").strip()
                secret = str(cfg.get("client_secret") or "").strip()
                redirect = str(cfg.get("redirect_uri") or "").strip()
                tenant = str(cfg.get("tenant") or "common").strip() or "common"
                if cid and secret and redirect:
                    return cid, secret, redirect, tenant
        except Exception:
            pass
    settings = get_settings()
    return (
        str(getattr(settings, "microsoft_calendar_client_id", None) or "").strip(),
        str(getattr(settings, "microsoft_calendar_client_secret", None) or "").strip(),
        str(getattr(settings, "microsoft_calendar_redirect_uri", None) or "").strip(),
        tenant,
    )


def platform_oauth_configured(db: Session | None = None) -> bool:
    client_id, client_secret, redirect, _tenant = _ms_platform_credentials(db)
    return bool(client_id and client_secret and redirect.startswith("http"))


def _authority_urls(tenant: str) -> tuple[str, str]:
    tenant_segment = str(tenant or "common").strip() or "common"
    auth = f"https://login.microsoftonline.com/{tenant_segment}/oauth2/v2.0/authorize"
    token = f"https://login.microsoftonline.com/{tenant_segment}/oauth2/v2.0/token"
    return auth, token


def test_microsoft_calendar_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect, _tenant = _ms_platform_credentials(db)
    if not client_id or not client_secret or not redirect:
        return {
            "ok": False,
            "detail": (
                "Microsoft Calendar client ID, secret, and redirect URI are required "
                "(Admin → Integrations → Microsoft 365 Calendar)"
            ),
        }
    if not redirect.startswith("http"):
        return {
            "ok": False,
            "detail": (
                "Redirect URI must be a full URL "
                "(https://api…/scheduling/oauth/microsoft-calendar/callback)"
            ),
        }
    return {
        "ok": True,
        "detail": "Microsoft Calendar OAuth credentials saved. Connect from Dashboard → Integrations.",
        "redirect_uri": redirect,
    }


def microsoft_calendar_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    ensure_can_connect_scheduling(db, org_id, "microsoft_calendar", replace=replace)
    client_id, _, redirect, tenant = _ms_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError(
            "Microsoft Calendar OAuth is not configured (Admin → Integrations → Microsoft 365 Calendar)"
        )
    authorize_url, _ = _authority_urls(tenant)
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": MICROSOFT_SCOPES,
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    }
    return f"{authorize_url}?{urlencode(params)}"


def microsoft_calendar_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect, tenant = _ms_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    _, token_url = _authority_urls(tenant)
    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
                "scope": MICROSOFT_SCOPES,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Microsoft token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Microsoft did not return an access token")

    headers = {"Authorization": f"Bearer {access_token}"}
    owner_name = ""
    owner_email = ""
    with httpx.Client(timeout=30.0) as client:
        me_res = client.get(MICROSOFT_GRAPH_ME, headers=headers)
    if me_res.status_code < 400:
        me = me_res.json() or {}
        owner_name = str(me.get("displayName") or "").strip()
        owner_email = str(me.get("mail") or me.get("userPrincipalName") or "").strip()

    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "provider": "microsoft_calendar",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "owner_name": owner_name,
        "owner_email": owner_email,
        "schedule_url": "",
        "schedule_name": "",
        "tenant": tenant,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def select_microsoft_calendar_schedule(
    db: Session,
    org_id: str,
    *,
    schedule_url: str,
    schedule_name: str = "",
) -> dict[str, Any]:
    url = str(schedule_url or "").strip()
    if not url.startswith("http"):
        raise ValueError("A valid Microsoft Bookings or Outlook booking page URL is required")
    cfg = dict(get_scheduling_config(db, org_id))
    if str(cfg.get("provider") or "").lower() != "microsoft_calendar":
        raise ValueError("Microsoft 365 Calendar is not connected")
    cfg["schedule_url"] = url
    cfg["schedule_name"] = (
        str(schedule_name or "").strip() or cfg.get("schedule_name") or "Microsoft Bookings page"
    )
    return save_scheduling_config(db, org_id, cfg)


def list_microsoft_calendar_calendars(db: Session, org_id: str) -> list[dict[str, Any]]:
    """Best-effort list of the user's Microsoft 365 calendars (for display only)."""
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "microsoft_calendar":
        raise ValueError("Microsoft 365 Calendar is not connected")
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        raise ValueError("Microsoft 365 Calendar connection is incomplete")
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        res = client.get(MICROSOFT_GRAPH_CALENDARS, headers=headers)
    if res.status_code >= 400:
        return out
    for row in (res.json() or {}).get("value") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        cal_id = str(row.get("id") or "").strip()
        if name and cal_id:
            out.append({"id": cal_id, "name": name, "url": ""})
    return out


def create_microsoft_calendar_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "microsoft_calendar":
        raise ValueError("Microsoft 365 Calendar is not connected for this organisation")
    base_url = str(cfg.get("schedule_url") or "").strip()
    if not base_url:
        raise ValueError("Paste a Microsoft Bookings page URL in Settings → Integrations before sending links")
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
