"""Zoho Recruit OAuth + candidate score writeback (real ATS path)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.services.crm_connection_service import get_crm_config_raw, save_crm_config_raw

logger = logging.getLogger(__name__)

ZOHO_RECRUIT_HOSTS: dict[str, tuple[str, str]] = {
    "com": ("accounts.zoho.com", "recruit.zoho.com"),
    "eu": ("accounts.zoho.eu", "recruit.zoho.eu"),
    "in": ("accounts.zoho.in", "recruit.zoho.in"),
    "au": ("accounts.zoho.com.au", "recruit.zoho.com.au"),
    "jp": ("accounts.zoho.jp", "recruit.zoho.jp"),
    "ca": ("accounts.zohocloud.ca", "recruit.zohocloud.ca"),
    "cn": ("accounts.zoho.com.cn", "recruit.zoho.com.cn"),
    "uk": ("accounts.zoho.uk", "recruit.zoho.uk"),
    "sa": ("accounts.zoho.sa", "recruit.zoho.sa"),
    "ae": ("accounts.zoho.ae", "recruit.zoho.ae"),
}

# Space-separated (same pattern as Zoho CRM in this codebase). Use group scopes —
# per-module names like modules.notes.ALL are rejected by some DCs as "Scope does not exist".
ZOHO_RECRUIT_SCOPES = "ZohoRecruit.modules.ALL ZohoRecruit.users.ALL"

PROVIDER_KEY = "zoho_recruit"
DEFAULT_REDIRECT = "https://api.voxbulk.com/partner/v1/oauth/zoho/callback"


def _normalize_dc(value: str | None) -> str:
    key = str(value or "com").strip().lower()
    aliases = {"us": "com", "usa": "com", "gb": "uk"}
    key = aliases.get(key, key)
    return key if key in ZOHO_RECRUIT_HOSTS else "com"


def _hosts(data_center: str) -> tuple[str, str]:
    return ZOHO_RECRUIT_HOSTS[_normalize_dc(data_center)]


def resolve_recruit_api_host(*, data_center: str | None = None, api_domain: str | None = None) -> str:
    """Recruit REST host. Token api_domain is often www.zohoapis.* (CRM) which 404s for /recruit/v2."""
    raw = str(api_domain or "").strip().lower()
    raw = raw.removeprefix("https://").removeprefix("http://").split("/")[0].strip()
    if raw.startswith("recruit.") and "zoho" in raw:
        return raw
    # Map zohoapis DC suffix → recruit host when possible.
    if "zohoapis.eu" in raw or raw.endswith(".eu"):
        return "recruit.zoho.eu"
    if "zohoapis.in" in raw:
        return "recruit.zoho.in"
    if "zohoapis.com.au" in raw or raw.endswith(".com.au"):
        return "recruit.zoho.com.au"
    if "zohoapis.jp" in raw:
        return "recruit.zoho.jp"
    if "zohoapis.com.cn" in raw:
        return "recruit.zoho.com.cn"
    if "zohocloud.ca" in raw:
        return "recruit.zohocloud.ca"
    if "zohoapis.sa" in raw:
        return "recruit.zoho.sa"
    if "zohoapis.ae" in raw:
        return "recruit.zoho.ae"
    if "zohoapis.uk" in raw or raw.endswith(".uk"):
        return "recruit.zoho.uk"
    if raw.startswith("www.zohoapis.") or "zohoapis" in raw:
        return "recruit.zoho.com"
    _, recruit_host = _hosts(data_center or "com")
    return recruit_host


def credentials_from_partner_config(config: dict[str, Any] | None) -> tuple[str, str, str, str]:
    cfg = config if isinstance(config, dict) else {}
    cid = str(cfg.get("client_id") or "").strip()
    secret = str(cfg.get("client_secret") or "").strip()
    redirect = str(cfg.get("redirect_uri") or DEFAULT_REDIRECT).strip() or DEFAULT_REDIRECT
    dc = _normalize_dc(str(cfg.get("data_centre") or cfg.get("data_center") or "com"))
    return cid, secret, redirect, dc


def get_recruit_config(db: Session, org_id: str) -> dict[str, Any]:
    return get_crm_config_raw(db, org_id, PROVIDER_KEY)


def recruit_status(db: Session, org_id: str, *, partner_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = get_recruit_config(db, org_id)
    cid, secret, redirect, partner_dc = credentials_from_partner_config(partner_config)
    dc = _normalize_dc(str(cfg.get("data_center") or partner_dc or "com"))
    api_host = resolve_recruit_api_host(data_center=dc, api_domain=str(cfg.get("api_domain") or ""))
    return {
        "connected": bool(str(cfg.get("access_token") or "").strip()),
        "oauth_app_ready": bool(cid and secret and redirect.startswith("http")),
        "account_name": cfg.get("account_name"),
        "data_center": dc,
        "api_domain": api_host,
        "connected_at": cfg.get("connected_at"),
        "redirect_uri": redirect,
        "scopes": ZOHO_RECRUIT_SCOPES,
    }


def oauth_start(*, org_id: str, partner_config: dict[str, Any]) -> str:
    cid, secret, redirect, dc = credentials_from_partner_config(partner_config)
    if not cid or not secret:
        raise ValueError(
            "Save Zoho OAuth Client ID and Client Secret first "
            "(from https://api-console.zoho.com — Server-based app with Recruit scopes)."
        )
    if not org_id:
        raise ValueError("Map a VoxBulk organisation before connecting Zoho Recruit")
    accounts_host, _ = _hosts(dc)
    state = f"{org_id}:zoho:{secrets.token_urlsafe(16)}"
    params = {
        "client_id": cid,
        "redirect_uri": redirect,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": ZOHO_RECRUIT_SCOPES,
        "state": state,
    }
    return f"https://{accounts_host}/oauth/v2/auth?{urlencode(params)}"


def oauth_disconnect(db: Session, org_id: str) -> dict[str, Any]:
    """Clear Recruit OAuth tokens for the mapped org (does not touch sales CRM)."""
    from app.models.organisation import Organisation

    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    org.zoho_recruit_config_json = None
    db.add(org)
    db.commit()
    return {
        "connected": False,
        "oauth_app_ready": False,
        "account_name": None,
        "data_center": None,
        "api_domain": None,
        "connected_at": None,
        "redirect_uri": DEFAULT_REDIRECT,
        "scopes": ZOHO_RECRUIT_SCOPES,
    }


def oauth_complete(
    db: Session,
    *,
    code: str,
    state: str,
    partner_config: dict[str, Any],
) -> dict[str, Any]:
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id = str(state).split(":", 1)[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")

    cid, secret, redirect, dc = credentials_from_partner_config(partner_config)
    if not cid or not secret:
        raise ValueError("Zoho OAuth Client ID/Secret not configured on Partners → Zoho")

    accounts_host, recruit_host = _hosts(dc)
    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            f"https://{accounts_host}/oauth/v2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": cid,
                "client_secret": secret,
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

    token_api_domain = str(token_data.get("api_domain") or "").strip()
    api_domain = resolve_recruit_api_host(data_center=dc, api_domain=token_api_domain or recruit_host)
    account_name = ""
    with httpx.Client(timeout=30.0) as client:
        user_res = client.get(
            f"https://{api_domain}/recruit/v2/users",
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
        "connected_at": datetime.utcnow().isoformat(),
    }
    save_crm_config_raw(db, org_id, PROVIDER_KEY, cfg)
    return recruit_status(db, org_id, partner_config=partner_config)


def _token_expired(cfg: dict[str, Any]) -> bool:
    raw = str(cfg.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        return datetime.utcnow() >= datetime.fromisoformat(raw) - timedelta(minutes=2)
    except Exception:
        return False


def _ensure_access_token(db: Session, org_id: str, partner_config: dict[str, Any] | None = None) -> tuple[str, str]:
    cfg = get_recruit_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    dc = _normalize_dc(str(cfg.get("data_center") or "com"))
    api_domain = resolve_recruit_api_host(data_center=dc, api_domain=str(cfg.get("api_domain") or ""))
    if not token:
        raise ValueError("Zoho Recruit is not connected for this organisation")
    if not _token_expired(cfg):
        return token, api_domain

    refresh = str(cfg.get("refresh_token") or "").strip()
    if not refresh:
        raise ValueError("Zoho Recruit token expired — reconnect OAuth")

    cid, secret, _, partner_dc = credentials_from_partner_config(partner_config or {})
    if not cid or not secret:
        raise ValueError("Zoho OAuth Client Secret missing — save it on Partners → Zoho and reconnect")

    accounts_host, recruit_host = _hosts(str(cfg.get("data_center") or partner_dc))
    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(
            f"https://{accounts_host}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": refresh,
            },
        )
    if token_res.status_code >= 400:
        raise ValueError(f"Zoho Recruit token refresh failed: {token_res.text[:300]}")
    token_data = token_res.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Zoho Recruit refresh did not return an access token")
    expires_in = int(token_data.get("expires_in") or 3600)
    cfg["access_token"] = access_token
    cfg["expires_at"] = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    cfg["api_domain"] = resolve_recruit_api_host(
        data_center=str(cfg.get("data_center") or partner_dc),
        api_domain=str(token_data.get("api_domain") or recruit_host),
    )
    save_crm_config_raw(db, org_id, PROVIDER_KEY, cfg)
    return access_token, str(cfg.get("api_domain") or recruit_host)


def write_screening_result(
    db: Session,
    *,
    org_id: str,
    candidate_id: str,
    score: int | None,
    result_status: str | None,
    report_url: str | None,
    partner_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Push AI screening outcome onto a Zoho Recruit Candidate record."""
    cid = str(candidate_id or "").strip()
    if not cid:
        return {"ok": False, "detail": "No Zoho candidate id (partner_reference_id)"}

    token, api_domain = _ensure_access_token(db, org_id, partner_config=partner_config)
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
    cfg = partner_config if isinstance(partner_config, dict) else {}
    score_field = str(cfg.get("score_field") or "").strip()
    status_field = str(cfg.get("status_field") or "").strip()
    report_field = str(cfg.get("report_url_field") or "").strip()

    record: dict[str, Any] = {"id": cid}
    if score_field and score is not None:
        record[score_field] = score
    if status_field and result_status:
        record[status_field] = result_status
    if report_field and report_url:
        record[report_field] = report_url

    note_body = (
        f"VoxBulk AI Voice Screening\n"
        f"Score: {score if score is not None else 'n/a'}\n"
        f"Status: {result_status or 'n/a'}\n"
        f"Report: {report_url or 'n/a'}"
    )

    updated = False
    note_ok = False
    with httpx.Client(timeout=30.0) as client:
        if len(record) > 1:
            res = client.put(
                f"https://{api_domain}/recruit/v2/Candidates",
                headers=headers,
                json={"data": [record]},
            )
            if res.status_code < 400:
                updated = True
            else:
                logger.warning(
                    "zoho_recruit_candidate_update_failed status=%s body=%s",
                    res.status_code,
                    res.text[:300],
                )

        note_res = client.post(
            f"https://{api_domain}/recruit/v2/Candidates/{cid}/Notes",
            headers=headers,
            json={
                "data": [
                    {
                        "Note_Title": "VoxBulk AI Screening",
                        "Note_Content": note_body,
                    }
                ]
            },
        )
        note_ok = note_res.status_code < 400
        if not note_ok:
            logger.warning(
                "zoho_recruit_note_failed status=%s body=%s",
                note_res.status_code,
                note_res.text[:300],
            )

    return {"ok": updated or note_ok, "candidate_updated": updated, "note_created": note_ok}
