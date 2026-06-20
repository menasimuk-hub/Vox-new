"""Org-level Cal.com OAuth and booking link generation."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.oauth_platform_test_service import (
    finalize_platform_test,
    mask_client_id,
    platform_credential_source,
    probe_confidential_oauth_token,
    validate_oauth_platform_fields,
)
from app.services.scheduling_connection_service import (
    get_scheduling_config,
    platform_oauth_configured,
    save_scheduling_config,
)

CAL_COM_AUTHORIZE_URL = "https://app.cal.com/auth/oauth2/authorize"
CAL_COM_TOKEN_URL = "https://api.cal.com/v2/auth/oauth2/token"
CAL_COM_OAUTH_SCOPES = "EVENT_TYPE_READ PROFILE_READ BOOKING_READ"


def _cal_com_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="cal_com")
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
        str(getattr(settings, "cal_com_client_id", None) or "").strip(),
        str(getattr(settings, "cal_com_client_secret", None) or "").strip(),
        str(getattr(settings, "cal_com_redirect_uri", None) or "").strip(),
    )


def test_cal_com_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect = _cal_com_platform_credentials(db)
    source = platform_credential_source(db, provider="cal_com")
    checks, fields_ok = validate_oauth_platform_fields(
        client_id=client_id,
        client_secret=client_secret,
        redirect=redirect,
        provider_label="Cal.com",
    )
    if not fields_ok:
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=CAL_COM_OAUTH_SCOPES,
        )

    checks.append(
        {
            "name": "credential_source",
            "status": "ok" if source == "admin_db" else "fail",
            "message": (
                "Using Admin-saved credentials"
                if source == "admin_db"
                else "Using CAL_COM_* env fallback — ensure Admin is enabled and saved, or update .env"
            ),
        }
    )

    probe = probe_confidential_oauth_token(
        token_url=CAL_COM_TOKEN_URL,
        payload={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": "voxbulk-platform-test-invalid-code",
            "redirect_uri": redirect,
        },
        use_json=True,
    )
    if probe["reason"] == "client_not_found":
        checks.append(
            {
                "name": "cal_com_api",
                "status": "fail",
                "message": (
                    "Cal.com rejected the client ID — use Developer OAuth at "
                    "app.cal.com/settings/developer/oauth (not Platform dashboard)"
                ),
            }
        )
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            redirect_uri=redirect,
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=CAL_COM_OAUTH_SCOPES,
        )
    if probe["reason"] == "invalid_secret":
        checks.append(
            {
                "name": "cal_com_api",
                "status": "fail",
                "message": "Cal.com recognized the client ID but rejected the client secret",
            }
        )
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            redirect_uri=redirect,
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=CAL_COM_OAUTH_SCOPES,
        )

    checks.append(
        {
            "name": "cal_com_api",
            "status": "ok",
            "message": probe["detail"],
        }
    )
    return finalize_platform_test(
        checks,
        ok=True,
        detail="Cal.com OAuth app verified. Connect from Dashboard → Integrations.",
        redirect_uri=redirect,
        credential_source=source,
        client_id_masked=mask_client_id(client_id),
        scopes=CAL_COM_OAUTH_SCOPES,
    )


def cal_com_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    from app.services.scheduling_connection_service import ensure_can_connect_scheduling

    ensure_can_connect_scheduling(db, org_id, "cal_com", replace=replace)
    client_id, _, redirect = _cal_com_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Cal.com OAuth is not configured (Admin → Integrations → Cal.com or CAL_COM_* env)")
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
        "scope": CAL_COM_OAUTH_SCOPES,
    }
    return f"{CAL_COM_AUTHORIZE_URL}?{urlencode(params)}"


def cal_com_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _cal_com_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            CAL_COM_TOKEN_URL,
            json={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Cal.com token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Cal.com did not return an access token")

    headers = {"Authorization": f"Bearer {access_token}", "cal-api-version": "2024-08-13"}
    with httpx.Client(timeout=30.0) as client:
        me_res = client.get("https://api.cal.com/v2/me", headers=headers)
    if me_res.status_code >= 400:
        raise ValueError(f"Cal.com profile lookup failed: {me_res.text[:300]}")
    me = me_res.json().get("data") or me_res.json() or {}
    owner_name = str(me.get("name") or me.get("username") or "").strip()
    owner_email = str(me.get("email") or "").strip()
    username = str(me.get("username") or "").strip()

    event_type_id = ""
    event_type_slug = ""
    event_type_url = ""
    with httpx.Client(timeout=30.0) as client:
        et_res = client.get("https://api.cal.com/v2/event-types", headers=headers, params={"username": username} if username else None)
    if et_res.status_code < 400:
        items = (et_res.json().get("data") or et_res.json().get("event_types") or [])
        if isinstance(items, list) and items:
            first = items[0] or {}
            event_type_id = str(first.get("id") or "").strip()
            event_type_slug = str(first.get("slug") or "").strip()
            event_type_url = str(first.get("link") or first.get("url") or "").strip()
            if not event_type_url and username and event_type_slug:
                event_type_url = f"https://cal.com/{username}/{event_type_slug}"

    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "provider": "cal_com",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "owner_name": owner_name,
        "owner_email": owner_email,
        "username": username,
        "event_type_id": event_type_id,
        "event_type_slug": event_type_slug,
        "event_type_url": event_type_url,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_scheduling_config(db, org_id, cfg)


def list_cal_com_event_types(db: Session, org_id: str) -> list[dict[str, Any]]:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "cal_com":
        raise ValueError("Cal.com is not connected")
    token = str(cfg.get("access_token") or "").strip()
    username = str(cfg.get("username") or "").strip()
    if not token:
        raise ValueError("Cal.com connection is incomplete")
    headers = {"Authorization": f"Bearer {token}", "cal-api-version": "2024-08-13"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get("https://api.cal.com/v2/event-types", headers=headers, params={"username": username} if username else None)
    if res.status_code >= 400:
        raise ValueError(f"Cal.com event types failed: {res.text[:300]}")
    items = res.json().get("data") or res.json().get("event_types") or []
    out: list[dict[str, Any]] = []
    for row in items if isinstance(items, list) else []:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip()
        link = str(row.get("link") or row.get("url") or "").strip()
        if not link and username and slug:
            link = f"https://cal.com/{username}/{slug}"
        out.append(
            {
                "id": str(row.get("id") or ""),
                "slug": slug,
                "title": str(row.get("title") or row.get("name") or slug),
                "url": link,
            }
        )
    return out


def select_cal_com_event_type(db: Session, org_id: str, *, event_type_id: str) -> dict[str, Any]:
    wanted = str(event_type_id or "").strip()
    if not wanted:
        raise ValueError("event_type_id is required")
    for row in list_cal_com_event_types(db, org_id):
        if str(row.get("id") or "") == wanted:
            cfg = dict(get_scheduling_config(db, org_id))
            cfg["event_type_id"] = wanted
            cfg["event_type_slug"] = str(row.get("slug") or "")
            cfg["event_type_url"] = str(row.get("url") or "")
            return save_scheduling_config(db, org_id, cfg)
    raise ValueError("Event type not found")


def create_cal_com_scheduling_link(
    db: Session,
    org_id: str,
    *,
    candidate_name: str,
    candidate_email: str = "",
) -> str:
    cfg = get_scheduling_config(db, org_id)
    if str(cfg.get("provider") or "").lower() != "cal_com":
        raise ValueError("Cal.com is not connected for this organisation")
    base_url = str(cfg.get("event_type_url") or "").strip()
    if not base_url:
        raise ValueError("Cal.com connection is incomplete — reconnect and pick an event type")
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


def cal_com_platform_ready(db: Session | None) -> bool:
    return platform_oauth_configured(db, "cal_com")
