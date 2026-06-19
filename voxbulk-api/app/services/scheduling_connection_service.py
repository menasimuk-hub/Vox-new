"""Org-level booking provider connection and scheduling link generation."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import get_encryptor
from app.models.organisation import Organisation
from app.services.booking_providers import (
    BOOKING_PROVIDERS,
    LEGACY_UNSUPPORTED_PROVIDERS,
    connected_account_display,
    provider_label,
)

CRONOFY_DATA_CENTERS: dict[str, tuple[str, str]] = {
    "us": ("app.cronofy.com", "api.cronofy.com"),
    "uk": ("app-uk.cronofy.com", "api-uk.cronofy.com"),
    "de": ("app-de.cronofy.com", "api-de.cronofy.com"),
    "au": ("app-au.cronofy.com", "api-au.cronofy.com"),
    "ca": ("app-ca.cronofy.com", "api-ca.cronofy.com"),
    "sg": ("app-sg.cronofy.com", "api-sg.cronofy.com"),
}


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_scheduling_config(db: Session, org_id: str) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        return {}
    cfg = _loads(getattr(org, "scheduling_config_json", None))
    token = str(cfg.get("access_token") or "").strip()
    if token.startswith("enc:"):
        try:
            cfg["access_token"] = get_encryptor().decrypt_str(token[4:])
        except Exception:
            cfg["access_token"] = ""
    return cfg


def save_scheduling_config(db: Session, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = dict(payload)
    provider = str(cfg.get("provider") or "").strip().lower()
    if provider in LEGACY_UNSUPPORTED_PROVIDERS:
        raise ValueError(f"{provider_label(provider)} is no longer supported — connect Calendly, Cal.com, Google Calendar, or HubSpot Meetings")
    if provider and provider not in BOOKING_PROVIDERS:
        raise ValueError(f"Unsupported booking provider: {provider}")
    token = str(cfg.get("access_token") or "").strip()
    if token and not token.startswith("enc:"):
        cfg["access_token"] = "enc:" + get_encryptor().encrypt_str(token)
    cfg["updated_at"] = datetime.utcnow().isoformat()
    org.scheduling_config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return scheduling_status(db, org_id)


def ensure_can_connect_scheduling(db: Session | None, org_id: str, provider: str, *, replace: bool = False) -> None:
    if db is None:
        return
    wanted = str(provider or "").strip().lower()
    if wanted not in BOOKING_PROVIDERS:
        raise ValueError(f"Unsupported booking provider: {provider}")
    cfg = get_scheduling_config(db, org_id)
    current = str(cfg.get("provider") or "").strip().lower()
    if not current or current == wanted:
        return
    if replace:
        org = db.get(Organisation, org_id)
        if org is not None:
            org.scheduling_config_json = None
            db.add(org)
            db.commit()
        return
    current_label = provider_label(current) or current
    raise ValueError(f"Disconnect {current_label} first or switch provider from Settings → Integrations")


def disconnect_scheduling(db: Session, org_id: str, *, provider: str | None = None) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = get_scheduling_config(db, org_id)
    connected_provider = str(cfg.get("provider") or "").strip().lower()
    if not connected_provider:
        return scheduling_status(db, org_id)
    if provider:
        wanted = str(provider).strip().lower()
        if wanted != connected_provider:
            raise ValueError(f"Not connected to {provider}")
    org.scheduling_config_json = None
    db.add(org)
    db.commit()
    return scheduling_status(db, org_id)


def scheduling_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_scheduling_config(db, org_id)
    provider = str(cfg.get("provider") or "").strip().lower()
    legacy_unsupported = provider in LEGACY_UNSUPPORTED_PROVIDERS
    connected = bool(provider) and not legacy_unsupported
    if provider == "calendly":
        connected = connected and bool(str(cfg.get("access_token") or "").strip())
    elif provider == "hubspot_meetings":
        from app.services.hubspot_connection_service import hubspot_status

        connected = connected and bool(str(cfg.get("meeting_link_url") or "").strip())
        hs = hubspot_status(db, org_id)
        if not hs.get("connected"):
            connected = False
    elif provider in ("cal_com", "google_calendar"):
        connected = connected and bool(str(cfg.get("access_token") or "").strip())
    elif legacy_unsupported:
        connected = False

    expires_at = cfg.get("expires_at")
    cal_connected = connected and provider == "calendly"
    cal_com_connected = connected and provider == "cal_com"
    google_connected = connected and provider == "google_calendar"
    hubspot_meetings_connected = connected and provider == "hubspot_meetings"
    cal_platform = platform_oauth_configured(db, "calendly")
    cal_com_platform = platform_oauth_configured(db, "cal_com")
    google_platform = platform_oauth_configured(db, "google_calendar")
    hubspot_platform = platform_oauth_configured(db, "hubspot")
    event_type_uri = str(cfg.get("event_type_uri") or "").strip()
    event_type_configured = False
    if cal_connected:
        event_type_configured = bool(event_type_uri)
    elif cal_com_connected:
        event_type_configured = bool(str(cfg.get("event_type_url") or cfg.get("event_type_id") or "").strip())
    elif google_connected:
        event_type_configured = bool(str(cfg.get("schedule_url") or "").strip())
    elif hubspot_meetings_connected:
        event_type_configured = bool(str(cfg.get("meeting_link_url") or "").strip())
    human_ready = connected and event_type_configured
    account = connected_account_display(cfg)
    return {
        "connected": connected,
        "provider": provider or None,
        "provider_label": provider_label(provider) if provider else None,
        "connected_account": account,
        "connected_provider_display": (
            f"{provider_label(provider)} · {account}" if provider and account else provider_label(provider)
        ),
        "calendly_connected": cal_connected,
        "cal_com_connected": cal_com_connected,
        "google_calendar_connected": google_connected,
        "hubspot_meetings_connected": hubspot_meetings_connected,
        "cronofy_connected": False,
        "legacy_unsupported_provider": provider if legacy_unsupported else None,
        "calendly_platform_configured": cal_platform,
        "cal_com_platform_configured": cal_com_platform,
        "google_calendar_platform_configured": google_platform,
        "hubspot_platform_configured": hubspot_platform,
        "cronofy_platform_configured": False,
        "interview_booking_ready": True,
        "interview_booking_mode": "voxbulk_native",
        "event_type_configured": event_type_configured,
        "human_scheduling_ready": human_ready,
        "human_scheduling_mode": provider if human_ready else None,
        "providers_available": list(BOOKING_PROVIDERS),
        "event_type_uri": cfg.get("event_type_uri"),
        "event_type_url": cfg.get("event_type_url") or cfg.get("schedule_url") or cfg.get("meeting_link_url"),
        "owner_name": cfg.get("owner_name"),
        "cronofy_sub": None,
        "expires_at": expires_at,
        "connected_at": cfg.get("connected_at"),
    }


def create_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    provider = str(cfg.get("provider") or "").strip().lower()
    if provider in LEGACY_UNSUPPORTED_PROVIDERS:
        raise ValueError("Cronofy is no longer supported — reconnect with Calendly, Cal.com, Google Calendar, or HubSpot Meetings")
    if provider == "calendly":
        return create_calendly_scheduling_link(db, org_id, candidate_name=candidate_name)
    if provider == "cal_com":
        from app.services.cal_com_connection_service import create_cal_com_scheduling_link

        return create_cal_com_scheduling_link(
            db, org_id, candidate_name=candidate_name, candidate_email=candidate_email
        )
    if provider == "google_calendar":
        from app.services.google_calendar_booking_service import create_google_calendar_scheduling_link

        return create_google_calendar_scheduling_link(
            db, org_id, candidate_name=candidate_name, candidate_email=candidate_email
        )
    if provider == "hubspot_meetings":
        from app.services.hubspot_meetings_service import create_hubspot_meetings_scheduling_link

        return create_hubspot_meetings_scheduling_link(
            db, org_id, candidate_name=candidate_name, candidate_email=candidate_email
        )
    raise ValueError("Connect a booking provider in Settings → Integrations before sending scheduling links")


def platform_oauth_configured(db: Session | None, provider: str) -> bool:
    provider = str(provider or "").strip().lower()
    if provider == "calendly":
        client_id, client_secret, redirect = _calendly_platform_credentials(db)
    elif provider == "cal_com":
        from app.services.cal_com_connection_service import _cal_com_platform_credentials

        client_id, client_secret, redirect = _cal_com_platform_credentials(db)
    elif provider == "google_calendar":
        from app.services.google_calendar_booking_service import _google_calendar_platform_credentials

        client_id, client_secret, redirect = _google_calendar_platform_credentials(db)
    elif provider == "hubspot":
        from app.services.hubspot_connection_service import platform_oauth_configured as hubspot_platform_ready

        return hubspot_platform_ready(db)
    elif provider == "cronofy":
        return False
    else:
        return False
    return bool(client_id and client_secret and redirect and redirect.startswith("http"))


def _cronofy_data_center(db: Session | None = None) -> str:
    dc = ""
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="cronofy")
            if enabled and isinstance(cfg, dict):
                dc = str(cfg.get("data_center") or "").strip().lower()
        except Exception:
            pass
    if not dc:
        dc = str(getattr(get_settings(), "cronofy_data_center", None) or "uk").strip().lower()
    return dc if dc in CRONOFY_DATA_CENTERS else "uk"


def _cronofy_hosts(db: Session | None = None) -> tuple[str, str]:
    return CRONOFY_DATA_CENTERS[_cronofy_data_center(db)]


def _calendly_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="calendly")
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
        str(getattr(settings, "calendly_client_id", None) or "").strip(),
        str(getattr(settings, "calendly_client_secret", None) or "").strip(),
        str(getattr(settings, "calendly_redirect_uri", None) or "").strip(),
    )


def _cronofy_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="cronofy")
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
        str(getattr(settings, "cronofy_client_id", None) or "").strip(),
        str(getattr(settings, "cronofy_client_secret", None) or "").strip(),
        str(getattr(settings, "cronofy_redirect_uri", None) or "").strip(),
    )


def test_calendly_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect = _calendly_platform_credentials(db)
    if not client_id or not client_secret or not redirect:
        return {"ok": False, "detail": "Calendly client ID, secret, and redirect URI are required (Admin → Integrations → Calendly)"}
    if not redirect.startswith("http"):
        return {"ok": False, "detail": "Redirect URI must be a full URL (https://api…/scheduling/oauth/calendly/callback)"}
    return {
        "ok": True,
        "detail": "Calendly OAuth credentials saved. Connect from Dashboard → System to complete OAuth.",
        "redirect_uri": redirect,
    }


def test_cronofy_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect = _cronofy_platform_credentials(db)
    if not client_id or not client_secret or not redirect:
        return {"ok": False, "detail": "Cronofy client ID, secret, and redirect URI are required (Admin → Integrations → Cronofy)"}
    if not redirect.startswith("http"):
        return {"ok": False, "detail": "Redirect URI must be a full URL (https://api…/scheduling/oauth/cronofy/callback)"}
    return {
        "ok": True,
        "detail": f"Cronofy OAuth credentials saved ({_cronofy_data_center(db).upper()} data center). Connect from Dashboard → System.",
        "redirect_uri": redirect,
        "data_center": _cronofy_data_center(db),
        "authorize_host": _cronofy_hosts(db)[0],
        "api_host": _cronofy_hosts(db)[1],
    }


def calendly_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    ensure_can_connect_scheduling(db, org_id, "calendly", replace=replace)
    client_id, _, redirect = _calendly_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Calendly OAuth is not configured (Admin → Integrations → Calendly or CALENDLY_* env)")
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
    }
    return f"https://auth.calendly.com/oauth/authorize?{urlencode(params)}"


def calendly_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _calendly_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            "https://auth.calendly.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Calendly token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Calendly did not return an access token")

    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        me_res = client.get("https://api.calendly.com/users/me", headers=headers)
    if me_res.status_code >= 400:
        raise ValueError(f"Calendly user lookup failed: {me_res.text[:300]}")
    me = me_res.json().get("resource") or {}
    owner_uri = str(me.get("uri") or "").strip()

    event_type_uri = ""
    with httpx.Client(timeout=30.0) as client:
        et_res = client.get(
            "https://api.calendly.com/event_types",
            headers=headers,
            params={"user": owner_uri, "active": "true", "count": 1},
        )
    if et_res.status_code < 400:
        items = (et_res.json().get("collection") or [])
        if items:
            event_type_uri = str(items[0].get("uri") or "").strip()

    expires_in = int(token_data.get("expires_in") or 7200)
    cfg = {
        "provider": "calendly",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "owner_uri": owner_uri,
        "owner_name": str(me.get("name") or ""),
        "event_type_uri": event_type_uri,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def create_calendly_scheduling_link(db: Session, org_id: str, *, candidate_name: str) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "calendly":
        raise ValueError("Calendly is not connected for this organisation")
    token = str(cfg.get("access_token") or "").strip()
    event_type = str(cfg.get("event_type_uri") or "").strip()
    if not token or not event_type:
        raise ValueError("Calendly connection is incomplete — reconnect and pick an event type")

    payload = {
        "max_event_count": 1,
        "owner": event_type,
        "owner_type": "EventType",
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            "https://api.calendly.com/scheduling_links",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if res.status_code >= 400:
        raise ValueError(f"Calendly scheduling link failed: {res.text[:300]}")
    resource = res.json().get("resource") or {}
    booking_url = str(resource.get("booking_url") or "").strip()
    if not booking_url:
        raise ValueError("Calendly returned no booking URL")
    return booking_url


def cronofy_oauth_start(*, org_id: str, db: Session | None = None) -> str:
    client_id, _, redirect = _cronofy_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Cronofy OAuth is not configured (Admin → Integrations → Cronofy or CRONOFY_* env)")
    app_host, _ = _cronofy_hosts(db)
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": "read_account read_events create_event",
        "state": state,
    }
    return f"https://{app_host}/oauth/authorize?{urlencode(params)}"


def cronofy_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _cronofy_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    _, api_host = _cronofy_hosts(db)
    token_url = f"https://{api_host}/oauth/token"
    userinfo_url = f"https://{api_host}/v1/userinfo"

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Cronofy token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Cronofy did not return an access token")

    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        me_res = client.get(userinfo_url, headers=headers)
    if me_res.status_code >= 400:
        raise ValueError(f"Cronofy user lookup failed: {me_res.text[:300]}")
    me = me_res.json() or {}
    sub = str(me.get("sub") or "").strip()
    name = str(me.get("name") or me.get("email") or "").strip()

    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "provider": "cronofy",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "cronofy_sub": sub,
        "owner_name": name,
        "data_center": _cronofy_data_center(db),
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def create_cronofy_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "cronofy":
        raise ValueError("Cronofy is not connected for this organisation")
    token = str(cfg.get("access_token") or "").strip()
    host_sub = str(cfg.get("cronofy_sub") or "").strip()
    if not token or not host_sub:
        raise ValueError("Cronofy connection is incomplete — reconnect in System settings")

    stored_dc = str(cfg.get("data_center") or "").strip().lower()
    if stored_dc and stored_dc in CRONOFY_DATA_CENTERS:
        _, api_host = CRONOFY_DATA_CENTERS[stored_dc]
    else:
        _, api_host = _cronofy_hosts(db)
    scheduling_url = f"https://{api_host}/v1/scheduling_requests"

    email = str(candidate_email or "").strip() or f"candidate+{secrets.token_hex(4)}@noreply.voxbulk.com"
    payload = {
        "host": {"sub": host_sub},
        "recipients": [
            {
                "email": email,
                "display_name": candidate_name or "Candidate",
                "slot_selector": True,
            }
        ],
        "event": {
            "summary": "Interview",
            "description": "Please book your interview slot.",
            "duration": {"minutes": 30},
        },
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            scheduling_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if res.status_code >= 400:
        raise ValueError(f"Cronofy scheduling request failed: {res.text[:300]}")
    data = res.json() or {}
    scheduling = data.get("scheduling_request") or data
    for key in ("scheduling_request_url", "url", "booking_url"):
        url = str(scheduling.get(key) or data.get(key) or "").strip()
        if url:
            return url
    links = scheduling.get("links") or data.get("links") or {}
    if isinstance(links, dict):
        url = str(links.get("scheduling_request") or links.get("booking") or "").strip()
        if url:
            return url
    raise ValueError("Cronofy returned no scheduling URL")
