"""Org-level Zoho CRM OAuth and candidate sync."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import (
    ensure_can_connect_crm,
    get_crm_config_raw,
    save_crm_config_raw,
)
from app.services.oauth_platform_test_service import (
    finalize_platform_test,
    mask_client_id,
    platform_credential_source,
    probe_confidential_oauth_token,
    validate_oauth_platform_fields,
)

ZOHO_DATA_CENTERS: dict[str, tuple[str, str]] = {
    "com": ("accounts.zoho.com", "www.zohoapis.com"),
    "eu": ("accounts.zoho.eu", "www.zohoapis.eu"),
    "in": ("accounts.zoho.in", "www.zohoapis.in"),
    "au": ("accounts.zoho.com.au", "www.zohoapis.com.au"),
    "jp": ("accounts.zoho.jp", "www.zohoapis.jp"),
    "ca": ("accounts.zohocloud.ca", "www.zohoapis.ca"),
    "cn": ("accounts.zoho.com.cn", "www.zohoapis.com.cn"),
}

ZOHO_CRM_SCOPES = "ZohoCRM.modules.contacts.ALL ZohoCRM.modules.deals.ALL ZohoBookings.services.ALL"


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_dc(value: str | None) -> str:
    key = str(value or "com").strip().lower()
    return key if key in ZOHO_DATA_CENTERS else "com"


def _zoho_hosts(data_center: str) -> tuple[str, str]:
    return ZOHO_DATA_CENTERS[_normalize_dc(data_center)]


def _zoho_platform_config(db: Session | None = None) -> tuple[dict[str, Any], bool]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoho_crm")
            if isinstance(cfg, dict):
                return cfg, bool(enabled)
        except Exception:
            pass
    return {}, False


def _zoho_platform_credentials(db: Session | None = None) -> tuple[str, str, str, str]:
    cfg, enabled = _zoho_platform_config(db)
    if enabled:
        cid = str(cfg.get("client_id") or "").strip()
        secret = str(cfg.get("client_secret") or "").strip()
        redirect = str(cfg.get("redirect_uri") or "").strip()
        dc = _normalize_dc(str(cfg.get("data_center") or "com"))
        if cid and secret and redirect:
            return cid, secret, redirect, dc
    return "", "", "", "com"


def platform_oauth_configured(db: Session | None = None) -> bool:
    client_id, client_secret, redirect, _ = _zoho_platform_credentials(db)
    return bool(client_id and client_secret and redirect.startswith("http"))


def test_zoho_crm_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect, dc = _zoho_platform_credentials(db)
    source = platform_credential_source(db, provider="zoho_crm")
    checks, fields_ok = validate_oauth_platform_fields(
        client_id=client_id,
        client_secret=client_secret,
        redirect=redirect,
        provider_label="Zoho CRM",
    )
    if not fields_ok:
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=ZOHO_CRM_SCOPES,
        )
    accounts_host, _ = _zoho_hosts(dc)
    token_url = f"https://{accounts_host}/oauth/v2/token"
    probe = probe_confidential_oauth_token(
        token_url=token_url,
        payload={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": "voxbulk-platform-test-invalid-code",
            "redirect_uri": redirect,
        },
        use_json=False,
    )
    checks.append(
        {
            "name": "zoho_api",
            "status": "ok" if probe["reason"] in {"invalid_code", "invalid_grant"} else "fail",
            "message": probe["detail"],
        }
    )
    ok = fields_ok and probe["reason"] in {"invalid_code", "invalid_grant"}
    return finalize_platform_test(
        checks,
        ok=ok,
        detail="Zoho CRM OAuth app verified. Connect from Dashboard → Integrations.",
        redirect_uri=redirect,
        credential_source=source,
        client_id_masked=mask_client_id(client_id),
        scopes=ZOHO_CRM_SCOPES,
        data_center=dc,
    )


def get_zoho_crm_config(db: Session, org_id: str) -> dict[str, Any]:
    return get_crm_config_raw(db, org_id, "zoho_crm")


def zoho_crm_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_zoho_crm_config(db, org_id)
    connected = bool(str(cfg.get("access_token") or "").strip())
    return {
        "connected": connected,
        "platform_configured": platform_oauth_configured(db),
        "data_center": _normalize_dc(str(cfg.get("data_center") or "com")),
        "account_name": cfg.get("account_name"),
        "api_domain": cfg.get("api_domain"),
        "auto_sync_shortlist": cfg.get("auto_sync_shortlist", True) is not False,
        "auto_sync_scheduling_send": cfg.get("auto_sync_scheduling_send", True) is not False,
        "expires_at": cfg.get("expires_at"),
        "connected_at": cfg.get("connected_at"),
    }


def update_zoho_crm_settings(
    db: Session,
    org_id: str,
    *,
    auto_sync_shortlist: bool | None = None,
    auto_sync_scheduling_send: bool | None = None,
) -> dict[str, Any]:
    cfg = get_zoho_crm_config(db, org_id)
    if auto_sync_shortlist is not None:
        cfg["auto_sync_shortlist"] = bool(auto_sync_shortlist)
    if auto_sync_scheduling_send is not None:
        cfg["auto_sync_scheduling_send"] = bool(auto_sync_scheduling_send)
    save_crm_config_raw(db, org_id, "zoho_crm", cfg)
    return zoho_crm_status(db, org_id)


def zoho_crm_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    ensure_can_connect_crm(db, org_id, "zoho_crm", replace=replace)
    client_id, _, redirect, dc = _zoho_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Zoho CRM OAuth is not configured (Admin → Integrations → Zoho CRM)")
    accounts_host, _ = _zoho_hosts(dc)
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": ZOHO_CRM_SCOPES,
        "state": state,
    }
    return f"https://{accounts_host}/oauth/v2/auth?{urlencode(params)}"


def zoho_crm_oauth_complete(db: Session, *, code: str, state: str, replace: bool = False) -> dict[str, Any]:
    client_id, client_secret, redirect, dc = _zoho_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")
    ensure_can_connect_crm(db, org_id, "zoho_crm", replace=replace)

    accounts_host, api_host = _zoho_hosts(dc)
    token_url = f"https://{accounts_host}/oauth/v2/token"
    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect,
                "code": code,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Zoho token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Zoho did not return an access token")

    api_domain = str(token_data.get("api_domain") or api_host).strip().lstrip("https://").lstrip("http://")
    account_name = ""
    with httpx.Client(timeout=30.0) as client:
        user_res = client.get(
            f"https://{api_domain}/crm/v2/users",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"type": "CurrentUser"},
        )
    if user_res.status_code < 400:
        users = (user_res.json() or {}).get("users") or []
        if users and isinstance(users[0], dict):
            account_name = str(users[0].get("full_name") or users[0].get("email") or "").strip()

    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "data_center": dc,
        "api_domain": api_domain,
        "account_name": account_name,
        "auto_sync_shortlist": True,
        "auto_sync_scheduling_send": True,
        "connected_at": datetime.utcnow().isoformat(),
    }
    save_crm_config_raw(db, org_id, "zoho_crm", cfg)
    return zoho_crm_status(db, org_id)


def _token_expired(cfg: dict[str, Any]) -> bool:
    raw = str(cfg.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw)
        return datetime.utcnow() >= expires - timedelta(minutes=2)
    except Exception:
        return False


def _ensure_access_token(db: Session, org_id: str) -> tuple[str, str]:
    cfg = get_zoho_crm_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    api_domain = str(cfg.get("api_domain") or "").strip()
    if not token:
        raise ValueError("Zoho CRM is not connected")
    if not _token_expired(cfg):
        return token, api_domain or _zoho_hosts(str(cfg.get("data_center") or "com"))[1]

    refresh = str(cfg.get("refresh_token") or "").strip()
    if not refresh:
        raise ValueError("Zoho refresh token missing — reconnect in Settings → Integrations")
    client_id, client_secret, _, dc = _zoho_platform_credentials(db)
    accounts_host, default_api = _zoho_hosts(str(cfg.get("data_center") or dc))
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            f"https://{accounts_host}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
            },
        )
    if res.status_code >= 400:
        raise ValueError(f"Zoho token refresh failed: {res.text[:200]}")
    data = res.json() or {}
    new_token = str(data.get("access_token") or "").strip()
    if not new_token:
        raise ValueError("Zoho refresh did not return an access token")
    cfg["access_token"] = new_token
    if data.get("api_domain"):
        cfg["api_domain"] = str(data.get("api_domain")).strip().lstrip("https://").lstrip("http://")
    expires_in = int(data.get("expires_in") or 3600)
    cfg["expires_at"] = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    save_crm_config_raw(db, org_id, "zoho_crm", cfg)
    return new_token, str(cfg.get("api_domain") or default_api)


def _split_name(name: str | None) -> tuple[str, str]:
    parts = str(name or "").strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0] if parts else "", "")


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    return _loads(order.config_json)


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    return _loads(recipient.result_json)


def _search_contact_by_email(token: str, api_domain: str, email: str) -> str | None:
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"https://{api_domain}/crm/v2/Contacts/search",
            headers=headers,
            params={"email": email},
        )
    if res.status_code >= 400:
        return None
    rows = (res.json() or {}).get("data") or []
    if not rows or not isinstance(rows[0], dict):
        return None
    return str(rows[0].get("id") or "").strip() or None


def sync_recipient_to_zoho_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    scheduling_url: str = "",
) -> dict[str, Any]:
    status = zoho_crm_status(db, org_id)
    if not status.get("connected"):
        raise ValueError("Zoho CRM is not connected")

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        raise ValueError("Candidate needs an email or phone to sync to Zoho CRM")

    token, api_domain = _ensure_access_token(db, org_id)
    first, last = _split_name(recipient.name)
    role = str(_order_config(order).get("role") or order.title or "Interview").strip()
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}

    record: dict[str, Any] = {"Last_Name": last or first or email or phone}
    if first:
        record["First_Name"] = first
    if email:
        record["Email"] = email
    if phone:
        record["Phone"] = phone
    if role:
        record["Title"] = role[:100]

    contact_id = _search_contact_by_email(token, api_domain, email) if email else None
    with httpx.Client(timeout=30.0) as client:
        if contact_id:
            res = client.put(
                f"https://{api_domain}/crm/v2/Contacts/{contact_id}",
                headers=headers,
                json={"data": [record]},
            )
        else:
            res = client.post(
                f"https://{api_domain}/crm/v2/Contacts",
                headers=headers,
                json={"data": [record]},
            )
    if res.status_code >= 400:
        raise ValueError(f"Zoho CRM contact sync failed: {res.text[:300]}")
    body = res.json() or {}
    rows = body.get("data") or []
    contact_id = str(rows[0].get("details", {}).get("id") or contact_id or rows[0].get("id") or "").strip()
    if not contact_id and rows:
        contact_id = str(rows[0].get("id") or "").strip()
    if not contact_id:
        raise ValueError("Zoho CRM did not return a contact ID")

    deal_payload = {
        "Deal_Name": f"{recipient.name or email} — {role}"[:120],
        "Contact_Name": {"id": contact_id},
    }
    deal_id = ""
    with httpx.Client(timeout=30.0) as client:
        deal_res = client.post(
            f"https://{api_domain}/crm/v2/Deals",
            headers=headers,
            json={"data": [deal_payload]},
        )
    if deal_res.status_code < 400:
        deal_rows = (deal_res.json() or {}).get("data") or []
        if deal_rows and isinstance(deal_rows[0], dict):
            deal_id = str(deal_rows[0].get("details", {}).get("id") or deal_rows[0].get("id") or "").strip()

    note_bits = [f"VoxBulk interview: {role}"]
    if recipient.ats_score is not None:
        note_bits.append(f"ATS score: {recipient.ats_score}")
    if scheduling_url:
        note_bits.append(f"Scheduling link: {scheduling_url}")

    merged = _recipient_result(recipient)
    merged.update(
        {
            "zoho_crm_contact_id": contact_id,
            "zoho_crm_deal_id": deal_id or None,
            "zoho_crm_synced_at": datetime.utcnow().isoformat(),
            "zoho_crm_sync_note": " · ".join(note_bits),
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    return {"ok": True, "contact_id": contact_id, "deal_id": deal_id or None}


def sync_shortlist_to_zoho_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient_ids: list[str],
) -> dict[str, Any]:
    status = zoho_crm_status(db, org_id)
    if not status.get("connected") or not status.get("auto_sync_shortlist"):
        return {"ok": True, "synced": 0, "skipped": True}

    from app.services.platform_catalog_service import ServiceOrderService

    all_recipients = ServiceOrderService.get_recipients(db, order.id)
    id_set = {str(x).strip() for x in recipient_ids if str(x).strip()}
    recipients = [r for r in all_recipients if r.id in id_set]

    synced = 0
    errors: list[str] = []
    for recipient in recipients:
        try:
            sync_recipient_to_zoho_crm(db, org_id, order=order, recipient=recipient)
            synced += 1
        except ValueError as exc:
            errors.append(f"{recipient.name or recipient.id}: {exc}")
    if synced:
        db.commit()
    return {"ok": True, "synced": synced, "errors": errors[:5]}
