"""Org-level Pipedrive OAuth and candidate sync."""

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

PIPEDRIVE_AUTHORIZE_URL = "https://oauth.pipedrive.com/oauth/authorize"
PIPEDRIVE_TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"
PIPEDRIVE_API_BASE = "https://api.pipedrive.com/v1"
PIPEDRIVE_SCOPES = "base deals:full contacts:full"


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _pipedrive_platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="pipedrive")
            if enabled:
                cid = str(cfg.get("client_id") or "").strip()
                secret = str(cfg.get("client_secret") or "").strip()
                redirect = str(cfg.get("redirect_uri") or "").strip()
                if cid and secret and redirect:
                    return cid, secret, redirect
        except Exception:
            pass
    return "", "", ""


def platform_oauth_configured(db: Session | None = None) -> bool:
    client_id, client_secret, redirect = _pipedrive_platform_credentials(db)
    return bool(client_id and client_secret and redirect.startswith("http"))


def test_pipedrive_platform_config(db: Session) -> dict[str, Any]:
    client_id, client_secret, redirect = _pipedrive_platform_credentials(db)
    source = platform_credential_source(db, provider="pipedrive")
    checks, fields_ok = validate_oauth_platform_fields(
        client_id=client_id,
        client_secret=client_secret,
        redirect=redirect,
        provider_label="Pipedrive",
    )
    if not fields_ok:
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=PIPEDRIVE_SCOPES,
        )
    probe = probe_confidential_oauth_token(
        token_url=PIPEDRIVE_TOKEN_URL,
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
            "name": "pipedrive_api",
            "status": "ok" if probe["reason"] in {"invalid_code", "invalid_grant"} else "fail",
            "message": probe["detail"],
        }
    )
    ok = probe["reason"] in {"invalid_code", "invalid_grant", "invalid_secret"} and fields_ok
    if probe["reason"] == "client_not_found":
        ok = False
    return finalize_platform_test(
        checks,
        ok=ok and probe["reason"] != "client_not_found",
        detail="Pipedrive OAuth app verified. Connect from Dashboard → Integrations."
        if ok
        else checks[-1]["message"],
        redirect_uri=redirect,
        credential_source=source,
        client_id_masked=mask_client_id(client_id),
        scopes=PIPEDRIVE_SCOPES,
    )


def get_pipedrive_config(db: Session, org_id: str) -> dict[str, Any]:
    return get_crm_config_raw(db, org_id, "pipedrive")


def pipedrive_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_pipedrive_config(db, org_id)
    connected = bool(str(cfg.get("access_token") or "").strip())
    return {
        "connected": connected,
        "platform_configured": platform_oauth_configured(db),
        "company_name": cfg.get("company_name"),
        "company_domain": cfg.get("company_domain"),
        "account_name": cfg.get("account_name"),
        "auto_sync_shortlist": cfg.get("auto_sync_shortlist", True) is not False,
        "auto_sync_scheduling_send": cfg.get("auto_sync_scheduling_send", True) is not False,
        "create_task_on_unhappy_score": cfg.get("create_task_on_unhappy_score") is True,
        "auto_sync_results_back": cfg.get("auto_sync_results_back") is not False,
        "expires_at": cfg.get("expires_at"),
        "connected_at": cfg.get("connected_at"),
    }


def update_pipedrive_settings(
    db: Session,
    org_id: str,
    *,
    auto_sync_shortlist: bool | None = None,
    auto_sync_scheduling_send: bool | None = None,
    create_task_on_unhappy_score: bool | None = None,
    auto_sync_results_back: bool | None = None,
) -> dict[str, Any]:
    cfg = get_pipedrive_config(db, org_id)
    if auto_sync_shortlist is not None:
        cfg["auto_sync_shortlist"] = bool(auto_sync_shortlist)
    if auto_sync_scheduling_send is not None:
        cfg["auto_sync_scheduling_send"] = bool(auto_sync_scheduling_send)
    if create_task_on_unhappy_score is not None:
        cfg["create_task_on_unhappy_score"] = bool(create_task_on_unhappy_score)
    if auto_sync_results_back is not None:
        cfg["auto_sync_results_back"] = bool(auto_sync_results_back)
    save_crm_config_raw(db, org_id, "pipedrive", cfg)
    return pipedrive_status(db, org_id)


def pipedrive_oauth_start(*, org_id: str, db: Session | None = None, replace: bool = False) -> str:
    ensure_can_connect_crm(db, org_id, "pipedrive", replace=replace)
    client_id, _, redirect = _pipedrive_platform_credentials(db)
    if not client_id or not redirect:
        raise ValueError("Pipedrive OAuth is not configured (Admin → Integrations → Pipedrive)")
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "state": state,
    }
    return f"{PIPEDRIVE_AUTHORIZE_URL}?{urlencode(params)}"


def _fetch_company_info(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(f"{PIPEDRIVE_API_BASE}/users/me", headers=headers)
    if res.status_code >= 400:
        return {}
    body = res.json() or {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    company = data.get("company_domain") or data.get("company_name") or ""
    return {
        "account_name": str(data.get("name") or "").strip(),
        "company_domain": str(data.get("company_domain") or "").strip(),
        "company_name": str(data.get("company_name") or company).strip(),
    }


def pipedrive_oauth_complete(db: Session, *, code: str, state: str, replace: bool = False) -> dict[str, Any]:
    client_id, client_secret, redirect = _pipedrive_platform_credentials(db)
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")
    ensure_can_connect_crm(db, org_id, "pipedrive", replace=replace)

    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            PIPEDRIVE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect,
                "code": code,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Pipedrive token exchange failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Pipedrive did not return an access token")

    info = _fetch_company_info(access_token)
    expires_in = int(token_data.get("expires_in") or 3600)
    cfg = {
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "auto_sync_shortlist": True,
        "auto_sync_scheduling_send": True,
        "connected_at": datetime.utcnow().isoformat(),
        **info,
    }
    save_crm_config_raw(db, org_id, "pipedrive", cfg)
    return pipedrive_status(db, org_id)


def _token_expired(cfg: dict[str, Any]) -> bool:
    raw = str(cfg.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw)
        return datetime.utcnow() >= expires - timedelta(minutes=2)
    except Exception:
        return False


def _ensure_access_token(db: Session, org_id: str) -> str:
    cfg = get_pipedrive_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        raise ValueError("Pipedrive is not connected")
    if not _token_expired(cfg):
        return token
    refresh = str(cfg.get("refresh_token") or "").strip()
    if not refresh:
        raise ValueError("Pipedrive refresh token missing — reconnect in Settings → Integrations")
    client_id, client_secret, _ = _pipedrive_platform_credentials(db)
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            PIPEDRIVE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
            },
        )
    if res.status_code >= 400:
        raise ValueError(f"Pipedrive token refresh failed: {res.text[:200]}")
    data = res.json() or {}
    new_token = str(data.get("access_token") or "").strip()
    if not new_token:
        raise ValueError("Pipedrive refresh did not return an access token")
    cfg["access_token"] = new_token
    if data.get("refresh_token"):
        cfg["refresh_token"] = str(data.get("refresh_token"))
    expires_in = int(data.get("expires_in") or 3600)
    cfg["expires_at"] = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    save_crm_config_raw(db, org_id, "pipedrive", cfg)
    return new_token


def _split_name(name: str | None) -> tuple[str, str]:
    parts = str(name or "").strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0] if parts else "", "")


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    return _loads(order.config_json)


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    return _loads(recipient.result_json)


def _search_person_by_email(token: str, email: str) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"{PIPEDRIVE_API_BASE}/persons/search",
            headers=headers,
            params={"term": email, "fields": "email", "limit": 1},
        )
    if res.status_code >= 400:
        return None
    items = ((res.json() or {}).get("data") or {}).get("items") or []
    if not items:
        return None
    person = items[0].get("item") if isinstance(items[0], dict) else None
    if not isinstance(person, dict):
        return None
    return str(person.get("id") or "").strip() or None


def sync_recipient_to_pipedrive(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    scheduling_url: str = "",
) -> dict[str, Any]:
    status = pipedrive_status(db, org_id)
    if not status.get("connected"):
        raise ValueError("Pipedrive is not connected")

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        raise ValueError("Candidate needs an email or phone to sync to Pipedrive")

    token = _ensure_access_token(db, org_id)
    first, last = _split_name(recipient.name)
    name = str(recipient.name or email or phone).strip()
    role = str(_order_config(order).get("role") or order.title or "Interview").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    person_id = _search_person_by_email(token, email) if email else None
    person_payload: dict[str, Any] = {"name": name}
    if email:
        person_payload["email"] = [{"value": email, "primary": True, "label": "work"}]
    if phone:
        person_payload["phone"] = [{"value": phone, "primary": True, "label": "work"}]

    with httpx.Client(timeout=30.0) as client:
        if person_id:
            res = client.put(f"{PIPEDRIVE_API_BASE}/persons/{person_id}", headers=headers, json=person_payload)
        else:
            res = client.post(f"{PIPEDRIVE_API_BASE}/persons", headers=headers, json=person_payload)
    if res.status_code >= 400:
        raise ValueError(f"Pipedrive person sync failed: {res.text[:300]}")
    body = res.json() or {}
    person_id = str((body.get("data") or {}).get("id") or person_id or "").strip()
    if not person_id:
        raise ValueError("Pipedrive did not return a person ID")

    deal_title = f"VoxBulk interview: {role}"
    if first or last:
        deal_title = f"{name} — {role}"
    deal_payload = {"title": deal_title[:255], "person_id": int(person_id)}
    with httpx.Client(timeout=30.0) as client:
        deal_res = client.post(f"{PIPEDRIVE_API_BASE}/deals", headers=headers, json=deal_payload)
    deal_id = ""
    if deal_res.status_code < 400:
        deal_id = str((deal_res.json() or {}).get("data", {}).get("id") or "").strip()

    note_bits = [f"VoxBulk interview: {role}"]
    if recipient.ats_score is not None:
        note_bits.append(f"ATS score: {recipient.ats_score}")
    if scheduling_url:
        note_bits.append(f"Scheduling link: {scheduling_url}")

    merged = _recipient_result(recipient)
    merged.update(
        {
            "pipedrive_person_id": person_id,
            "pipedrive_deal_id": deal_id or None,
            "pipedrive_synced_at": datetime.utcnow().isoformat(),
            "pipedrive_sync_note": " · ".join(note_bits),
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)

    domain = str(get_pipedrive_config(db, org_id).get("company_domain") or "").strip()
    contact_url = f"https://{domain}.pipedrive.com/person/{person_id}" if domain else ""
    return {"ok": True, "person_id": person_id, "deal_id": deal_id or None, "contact_url": contact_url}


def sync_shortlist_to_pipedrive(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient_ids: list[str],
) -> dict[str, Any]:
    status = pipedrive_status(db, org_id)
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
            sync_recipient_to_pipedrive(db, org_id, order=order, recipient=recipient)
            synced += 1
        except ValueError as exc:
            errors.append(f"{recipient.name or recipient.id}: {exc}")
    if synced:
        db.commit()
    return {"ok": True, "synced": synced, "errors": errors[:5]}
