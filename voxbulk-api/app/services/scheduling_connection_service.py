"""Org-level Calendly / Cronofy connection and scheduling link generation."""

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
    token = str(cfg.get("access_token") or "").strip()
    if token and not token.startswith("enc:"):
        cfg["access_token"] = "enc:" + get_encryptor().encrypt_str(token)
    cfg["updated_at"] = datetime.utcnow().isoformat()
    org.scheduling_config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return scheduling_status(db, org_id)


def scheduling_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_scheduling_config(db, org_id)
    provider = str(cfg.get("provider") or "").strip().lower()
    connected = bool(provider and str(cfg.get("access_token") or "").strip())
    expires_at = cfg.get("expires_at")
    return {
        "connected": connected,
        "provider": provider or None,
        "providers_available": ["calendly", "cronofy"],
        "event_type_uri": cfg.get("event_type_uri"),
        "owner_name": cfg.get("owner_name"),
        "cronofy_sub": cfg.get("cronofy_sub"),
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
    if provider == "calendly":
        return create_calendly_scheduling_link(db, org_id, candidate_name=candidate_name)
    if provider == "cronofy":
        return create_cronofy_scheduling_link(
            db,
            org_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
        )
    raise ValueError("Connect Calendly or Cronofy in System settings before sending scheduling links")


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
        "detail": "Cronofy OAuth credentials saved. Connect from Dashboard → System to complete OAuth.",
        "redirect_uri": redirect,
    }


def calendly_oauth_start(*, org_id: str, db: Session | None = None) -> str:
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
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": "read_account read_events create_event",
        "state": state,
    }
    return f"https://app.cronofy.com/oauth/authorize?{urlencode(params)}"


def cronofy_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _cronofy_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            "https://api.cronofy.com/oauth/token",
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
        me_res = client.get("https://api.cronofy.com/v1/userinfo", headers=headers)
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
            "https://api.cronofy.com/v1/scheduling_requests",
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
