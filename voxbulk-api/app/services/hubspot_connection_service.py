"""Org-level HubSpot OAuth and candidate contact sync."""

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
from app.models.service_order import ServiceOrder, ServiceOrderRecipient

HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"
HUBSPOT_SCOPES = "crm.objects.contacts.read crm.objects.contacts.write oauth"


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _encrypt_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("enc:"):
        return token
    return "enc:" + get_encryptor().encrypt_str(token)


def _decrypt_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("enc:"):
        try:
            return get_encryptor().decrypt_str(token[4:])
        except Exception:
            return ""
    return token


def get_hubspot_config(db: Session, org_id: str) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        return {}
    cfg = _loads(getattr(org, "hubspot_config_json", None))
    for key in ("access_token", "refresh_token"):
        cfg[key] = _decrypt_token(str(cfg.get(key) or ""))
    return cfg


def save_hubspot_config(db: Session, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = dict(payload)
    for key in ("access_token", "refresh_token"):
        if key in cfg:
            cfg[key] = _encrypt_token(str(cfg.get(key) or ""))
    cfg["updated_at"] = datetime.utcnow().isoformat()
    org.hubspot_config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return hubspot_status(db, org_id)


def hubspot_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_hubspot_config(db, org_id)
    connected = bool(str(cfg.get("access_token") or "").strip())
    platform = platform_oauth_configured(db)
    platform_mode = _hubspot_platform_auth_mode(db)
    org_mode = str(cfg.get("auth_mode") or platform_mode).strip().lower()
    return {
        "connected": connected,
        "platform_configured": platform,
        "auth_mode": platform_mode,
        "connection_mode": org_mode if connected else None,
        "uses_oauth_connect": platform_mode == "oauth",
        "uses_access_token": platform_mode == "private_app",
        "hub_id": cfg.get("hub_id"),
        "hub_domain": cfg.get("hub_domain"),
        "account_name": cfg.get("account_name"),
        "auto_sync_shortlist": cfg.get("auto_sync_shortlist", True) is not False,
        "auto_sync_scheduling_send": cfg.get("auto_sync_scheduling_send", True) is not False,
        "expires_at": cfg.get("expires_at"),
        "connected_at": cfg.get("connected_at"),
    }


def update_hubspot_settings(
    db: Session,
    org_id: str,
    *,
    auto_sync_shortlist: bool | None = None,
    auto_sync_scheduling_send: bool | None = None,
) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = _loads(org.hubspot_config_json)
    if auto_sync_shortlist is not None:
        cfg["auto_sync_shortlist"] = bool(auto_sync_shortlist)
    if auto_sync_scheduling_send is not None:
        cfg["auto_sync_scheduling_send"] = bool(auto_sync_scheduling_send)
    org.hubspot_config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(org)
    db.commit()
    return hubspot_status(db, org_id)


def disconnect_hubspot(db: Session, org_id: str) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    org.hubspot_config_json = None
    db.add(org)
    db.commit()
    return hubspot_status(db, org_id)


def _hubspot_platform_config(db: Session | None = None) -> tuple[dict[str, Any], bool]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="hubspot")
            if isinstance(cfg, dict):
                return cfg, bool(enabled)
        except Exception:
            pass
    return {}, False


def _hubspot_platform_auth_mode(db: Session | None = None) -> str:
    cfg, enabled = _hubspot_platform_config(db)
    if not enabled:
        return "private_app"
    mode = str(cfg.get("auth_mode") or "private_app").strip().lower()
    return mode if mode in {"oauth", "private_app"} else "private_app"


def _hubspot_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    cfg, enabled = _hubspot_platform_config(db)
    if enabled and _hubspot_platform_auth_mode(db) == "oauth":
        cid = str(cfg.get("client_id") or "").strip()
        secret = str(cfg.get("client_secret") or "").strip()
        redirect = str(cfg.get("redirect_uri") or "").strip()
        if cid and secret and redirect:
            return cid, secret, redirect
    settings = get_settings()
    return (
        str(getattr(settings, "hubspot_client_id", None) or "").strip(),
        str(getattr(settings, "hubspot_client_secret", None) or "").strip(),
        str(getattr(settings, "hubspot_redirect_uri", None) or "").strip(),
    )


def platform_oauth_configured(db: Session | None = None) -> bool:
    cfg, enabled = _hubspot_platform_config(db)
    if enabled:
        if _hubspot_platform_auth_mode(db) == "private_app":
            return True
        client_id, client_secret, redirect = _hubspot_platform_credentials(db)
        return bool(client_id and client_secret and redirect.startswith("http"))
    client_id, client_secret, redirect = _hubspot_platform_credentials(None)
    return bool(client_id and client_secret and redirect.startswith("http"))


def _fetch_token_info(access_token: str) -> dict[str, Any]:
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("Access token is required")
    with httpx.Client(timeout=30.0) as client:
        info_res = client.get(f"https://api.hubapi.com/oauth/v1/access-tokens/{token}")
    if info_res.status_code >= 400:
        with httpx.Client(timeout=30.0) as client:
            probe = client.get(
                f"{HUBSPOT_CONTACTS_URL}?limit=1",
                headers={"Authorization": f"Bearer {token}"},
            )
        if probe.status_code >= 400:
            raise ValueError(f"HubSpot access token invalid: {info_res.text[:200]}")
        return {"hub_id": "", "hub_domain": "", "account_name": "Private app"}
    info = info_res.json() or {}
    return {
        "hub_id": str(info.get("hub_id") or "").strip(),
        "hub_domain": str(info.get("hub_domain") or "").strip(),
        "account_name": str(info.get("user") or info.get("user_id") or "HubSpot").strip(),
    }


def verify_hubspot_platform_config(db: Session) -> dict[str, Any]:
    cfg, enabled = _hubspot_platform_config(db)
    if not enabled:
        return {"ok": False, "detail": "Enable HubSpot in Admin → Integrations → HubSpot first"}
    mode = _hubspot_platform_auth_mode(db)
    if mode == "private_app":
        return {
            "ok": True,
            "auth_mode": "private_app",
            "detail": "Service key mode enabled. Each company pastes their HubSpot Service key in Dashboard → Integrations (no OAuth secret needed).",
        }
    client_id, client_secret, redirect = _hubspot_platform_credentials(db)
    if not client_id or not client_secret or not redirect:
        return {
            "ok": False,
            "detail": "OAuth mode requires Client ID, Client secret, and redirect URI (or switch auth mode to Private app).",
        }
    if not redirect.startswith("http"):
        return {"ok": False, "detail": "Redirect URI must be a full URL (https://api…/hubspot/oauth/callback)"}
    return {
        "ok": True,
        "auth_mode": "oauth",
        "detail": "HubSpot OAuth credentials saved. Companies click Connect HubSpot in Dashboard → Integrations.",
        "redirect_uri": redirect,
        "scopes": HUBSPOT_SCOPES,
    }


def connect_hubspot_access_token(db: Session, org_id: str, access_token: str) -> dict[str, Any]:
    if not platform_oauth_configured(db):
        raise ValueError("HubSpot is not enabled in admin settings")
    info = _fetch_token_info(access_token)
    cfg = {
        "auth_mode": "private_app",
        "access_token": access_token.strip(),
        "refresh_token": "",
        "hub_id": info.get("hub_id"),
        "hub_domain": info.get("hub_domain"),
        "account_name": info.get("account_name"),
        "auto_sync_shortlist": True,
        "auto_sync_scheduling_send": True,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_hubspot_config(db, org_id, cfg)


def hubspot_oauth_start(*, org_id: str, db: Session | None = None) -> str:
    if _hubspot_platform_auth_mode(db) != "oauth":
        raise ValueError("HubSpot is in Private app mode — paste your access token in Dashboard → Integrations")
    client_id, _, redirect = _hubspot_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("HubSpot OAuth is not configured (Admin → Integrations → HubSpot or HUBSPOT_* env)")
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": HUBSPOT_SCOPES,
        "state": state,
    }
    return f"{HUBSPOT_AUTHORIZE_URL}?{urlencode(params)}"


def hubspot_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _hubspot_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            HUBSPOT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect,
                "code": code,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"HubSpot token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("HubSpot did not return an access token")

    hub_id = ""
    hub_domain = ""
    account_name = ""
    with httpx.Client(timeout=30.0) as client:
        info_res = client.get(f"https://api.hubapi.com/oauth/v1/access-tokens/{access_token}")
    if info_res.status_code < 400:
        info = info_res.json() or {}
        hub_id = str(info.get("hub_id") or "").strip()
        hub_domain = str(info.get("hub_domain") or "").strip()
        account_name = str(info.get("user") or info.get("user_id") or "").strip()

    expires_in = int(token_data.get("expires_in") or 1800)
    cfg = {
        "auth_mode": "oauth",
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "hub_id": hub_id,
        "hub_domain": hub_domain,
        "account_name": account_name,
        "auto_sync_shortlist": True,
        "auto_sync_scheduling_send": True,
        "connected_at": datetime.utcnow().isoformat(),
    }
    return save_hubspot_config(db, org_id, cfg)


def _token_expired(cfg: dict[str, Any]) -> bool:
    raw = str(cfg.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw)
        return datetime.utcnow() >= expires - timedelta(minutes=2)
    except Exception:
        return False


def _refresh_access_token(db: Session, org_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    refresh = str(cfg.get("refresh_token") or "").strip()
    if not refresh:
        raise ValueError("HubSpot refresh token missing — reconnect HubSpot in System settings")
    client_id, client_secret, _ = _hubspot_platform_credentials(db)
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            HUBSPOT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
            },
        )
    if res.status_code >= 400:
        raise ValueError(f"HubSpot token refresh failed: {res.text[:300]}")
    data = res.json()
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("HubSpot token refresh returned no access token")
    expires_in = int(data.get("expires_in") or 1800)
    updated = {
        **cfg,
        "access_token": access_token,
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
    }
    new_refresh = str(data.get("refresh_token") or "").strip()
    if new_refresh:
        updated["refresh_token"] = new_refresh
    save_hubspot_config(db, org_id, updated)
    return get_hubspot_config(db, org_id)


def _ensure_access_token(db: Session, org_id: str) -> str:
    cfg = get_hubspot_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        raise ValueError("HubSpot is not connected for this organisation")
    if str(cfg.get("auth_mode") or "").lower() == "private_app":
        return token
    if _token_expired(cfg) and str(cfg.get("refresh_token") or "").strip():
        cfg = _refresh_access_token(db, org_id, cfg)
        token = str(cfg.get("access_token") or "").strip()
    return token


def _split_name(name: str | None) -> tuple[str, str]:
    raw = str(name or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _search_contact_by_email(token: str, email: str) -> str | None:
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": email,
                    }
                ]
            }
        ],
        "limit": 1,
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            f"{HUBSPOT_CONTACTS_URL}/search",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if res.status_code >= 400:
        return None
    results = (res.json() or {}).get("results") or []
    if not results:
        return None
    return str(results[0].get("id") or "").strip() or None


def sync_recipient_to_hubspot(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    scheduling_url: str = "",
    lifecycle_stage: str = "lead",
) -> dict[str, Any]:
    """Create or update a HubSpot contact for an interview candidate."""
    status = hubspot_status(db, org_id)
    if not status.get("connected"):
        raise ValueError("HubSpot is not connected")

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        raise ValueError("Candidate needs an email or phone to sync to HubSpot")

    token = _ensure_access_token(db, org_id)
    first, last = _split_name(recipient.name)
    role = str(_order_config(order).get("role") or order.title or "Interview").strip()
    properties: dict[str, str] = {}
    if email:
        properties["email"] = email
    if phone:
        properties["phone"] = phone
    if first:
        properties["firstname"] = first
    if last:
        properties["lastname"] = last
    if role:
        properties["jobtitle"] = role[:100]
    if lifecycle_stage:
        properties["lifecyclestage"] = lifecycle_stage

    note_bits = [f"VoxBulk interview: {role}"]
    if recipient.ats_score is not None:
        note_bits.append(f"ATS score: {recipient.ats_score}")
    if scheduling_url:
        note_bits.append(f"Scheduling link: {scheduling_url}")
    properties["hs_lead_status"] = "OPEN"

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    contact_id = _search_contact_by_email(token, email) if email else None

    with httpx.Client(timeout=30.0) as client:
        if contact_id:
            res = client.patch(
                f"{HUBSPOT_CONTACTS_URL}/{contact_id}",
                headers=headers,
                json={"properties": properties},
            )
        else:
            res = client.post(
                HUBSPOT_CONTACTS_URL,
                headers=headers,
                json={"properties": properties},
            )
    if res.status_code >= 400:
        raise ValueError(f"HubSpot contact sync failed: {res.text[:300]}")
    body = res.json() or {}
    contact_id = str(body.get("id") or contact_id or "").strip()
    if not contact_id:
        raise ValueError("HubSpot did not return a contact ID")

    merged = _recipient_result(recipient)
    merged.update(
        {
            "hubspot_contact_id": contact_id,
            "hubspot_synced_at": datetime.utcnow().isoformat(),
            "hubspot_sync_note": " · ".join(note_bits),
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)

    portal = str(get_hubspot_config(db, org_id).get("hub_id") or "").strip()
    contact_url = f"https://app.hubspot.com/contacts/{portal}/contact/{contact_id}" if portal else ""
    return {"ok": True, "contact_id": contact_id, "contact_url": contact_url}


def sync_shortlist_to_hubspot(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient_ids: list[str],
) -> dict[str, Any]:
    status = hubspot_status(db, org_id)
    if not status.get("connected") or not status.get("auto_sync_shortlist"):
        return {"ok": True, "synced": 0, "skipped": True}

    recipients = [r for r in order.recipients if r.id in set(recipient_ids)] if hasattr(order, "recipients") else []
    if not recipients:
        from app.services.platform_catalog_service import ServiceOrderService

        all_recipients = ServiceOrderService.get_recipients(db, order.id)
        id_set = {str(x).strip() for x in recipient_ids if str(x).strip()}
        recipients = [r for r in all_recipients if r.id in id_set]

    synced = 0
    errors: list[str] = []
    for recipient in recipients:
        try:
            sync_recipient_to_hubspot(db, org_id, order=order, recipient=recipient)
            synced += 1
        except ValueError as exc:
            errors.append(f"{recipient.name or recipient.id}: {exc}")
    if synced:
        db.commit()
    return {"ok": True, "synced": synced, "errors": errors}
