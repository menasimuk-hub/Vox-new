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


DATA_CENTER_OPTIONS: tuple[dict[str, str], ...] = (
    {"id": "eu", "label": "Europe (EU)", "accounts": "accounts.zoho.eu"},
    {"id": "uk", "label": "United Kingdom", "accounts": "accounts.zoho.uk"},
    {"id": "com", "label": "United States", "accounts": "accounts.zoho.com"},
    {"id": "ca", "label": "Canada", "accounts": "accounts.zohocloud.ca"},
    {"id": "in", "label": "India", "accounts": "accounts.zoho.in"},
    {"id": "au", "label": "Australia", "accounts": "accounts.zoho.com.au"},
    {"id": "jp", "label": "Japan", "accounts": "accounts.zoho.jp"},
    {"id": "ae", "label": "UAE", "accounts": "accounts.zoho.ae"},
    {"id": "sa", "label": "Saudi Arabia", "accounts": "accounts.zoho.sa"},
    {"id": "cn", "label": "China", "accounts": "accounts.zoho.com.cn"},
)


def load_partner_oauth_config(db: Session) -> dict[str, Any]:
    """Platform Client ID/Secret from Admin → Partners → Zoho."""
    from sqlalchemy import select

    from app.models.partner import PartnerProvider

    row = db.execute(select(PartnerProvider).where(PartnerProvider.key == "zoho")).scalar_one_or_none()
    if row is None:
        return {}
    try:
        import json

        data = json.loads(row.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def partner_provider_enabled(db: Session) -> bool:
    from sqlalchemy import select

    from app.models.partner import PartnerProvider

    row = db.execute(select(PartnerProvider).where(PartnerProvider.key == "zoho")).scalar_one_or_none()
    return bool(row and row.enabled)


def platform_oauth_configured(db: Session | None = None) -> bool:
    if db is None:
        return False
    cfg = load_partner_oauth_config(db)
    cid, secret, redirect, _ = credentials_from_partner_config(cfg)
    return bool(cid and secret and redirect.startswith("http"))


def get_recruit_config(db: Session, org_id: str) -> dict[str, Any]:
    return get_crm_config_raw(db, org_id, PROVIDER_KEY)


def recruit_status(db: Session, org_id: str, *, partner_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = get_recruit_config(db, org_id)
    partner_cfg = partner_config if isinstance(partner_config, dict) else load_partner_oauth_config(db)
    cid, secret, redirect, partner_dc = credentials_from_partner_config(partner_cfg)
    dc = _normalize_dc(str(cfg.get("data_center") or partner_dc or "com"))
    api_host = resolve_recruit_api_host(data_center=dc, api_domain=str(cfg.get("api_domain") or ""))
    return {
        "connected": bool(str(cfg.get("access_token") or "").strip()),
        "oauth_app_ready": bool(cid and secret and redirect.startswith("http")),
        "platform_configured": bool(cid and secret and redirect.startswith("http")),
        "account_name": cfg.get("account_name"),
        "data_center": dc if str(cfg.get("access_token") or "").strip() else None,
        "api_domain": api_host if str(cfg.get("access_token") or "").strip() else None,
        "connected_at": cfg.get("connected_at"),
        "redirect_uri": redirect,
        "scopes": ZOHO_RECRUIT_SCOPES,
        "data_centers": list(DATA_CENTER_OPTIONS),
    }


def _parse_oauth_state(state: str) -> tuple[str, str]:
    """Return (org_id, data_center). State: org_id:zoho:dc:nonce"""
    parts = [p for p in str(state or "").split(":") if p != ""]
    if len(parts) < 1:
        raise ValueError("Invalid OAuth state")
    org_id = parts[0].strip()
    if not org_id:
        raise ValueError("Invalid OAuth state")
    dc = "com"
    if len(parts) >= 3 and parts[1].lower() == "zoho":
        dc = _normalize_dc(parts[2])
    return org_id, dc


def oauth_start(
    *,
    org_id: str,
    partner_config: dict[str, Any] | None = None,
    data_center: str | None = None,
    db: Session | None = None,
) -> str:
    cfg = (
        partner_config
        if isinstance(partner_config, dict) and (partner_config.get("client_id") or partner_config.get("client_secret"))
        else (load_partner_oauth_config(db) if db is not None else {})
    )
    cid, secret, redirect, _fallback_dc = credentials_from_partner_config(cfg)
    dc = _normalize_dc(data_center or _fallback_dc or "com")
    if not cid or not secret:
        raise ValueError(
            "Zoho Recruit is not configured yet. An admin must save Client ID and Secret "
            "under Admin → Partners → Zoho."
        )
    if not org_id:
        raise ValueError("Organisation required to connect Zoho Recruit")
    accounts_host, _ = _hosts(dc)
    state = f"{org_id}:zoho:{dc}:{secrets.token_urlsafe(16)}"
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
    """Clear Recruit OAuth tokens for the org (does not touch sales CRM)."""
    from app.models.organisation import Organisation

    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    org.zoho_recruit_config_json = None
    db.add(org)
    db.commit()
    return recruit_status(db, org_id)


def oauth_complete(
    db: Session,
    *,
    code: str,
    state: str,
    partner_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not code or not state:
        raise ValueError("Missing OAuth code or state")
    org_id, dc = _parse_oauth_state(state)

    cfg = partner_config if isinstance(partner_config, dict) else load_partner_oauth_config(db)
    cid, secret, redirect, _ = credentials_from_partner_config(cfg)
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
    stored = {
        "access_token": access_token,
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        "data_center": dc,
        "api_domain": api_domain,
        "account_name": account_name,
        "connected_at": datetime.utcnow().isoformat(),
    }
    save_crm_config_raw(db, org_id, PROVIDER_KEY, stored)
    return recruit_status(db, org_id, partner_config=cfg)


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

    cid, secret, _, partner_dc = credentials_from_partner_config(
        partner_config
        if isinstance(partner_config, dict) and (partner_config.get("client_id") or partner_config.get("client_secret"))
        else load_partner_oauth_config(db)
    )
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


def _candidate_row_from_zoho(row: dict[str, Any]) -> dict[str, Any] | None:
    cid = str(row.get("id") or "").strip()
    if not cid:
        return None
    phone = str(row.get("Mobile") or row.get("Phone") or row.get("Secondary_Phone") or "").strip()
    email = str(row.get("Email") or "").strip()
    name = str(row.get("Full_Name") or row.get("Last_Name") or row.get("First_Name") or "").strip()
    stage = str(
        row.get("Candidate_Status")
        or row.get("Application_Status")
        or row.get("Stage")
        or ""
    ).strip()
    job_lookup = row.get("Job_Opening_Name") or row.get("Job_Opening_ID") or {}
    job_id = ""
    job_name = ""
    if isinstance(job_lookup, dict):
        job_id = str(job_lookup.get("id") or "").strip()
        job_name = str(job_lookup.get("name") or "").strip()
    elif job_lookup:
        job_name = str(job_lookup).strip()
    return {
        "id": cid,
        "name": name,
        "email": email,
        "phone": phone,
        "job_title": str(row.get("Current_Job_Title") or row.get("Skill_Set") or job_name or "").strip(),
        "stage": stage,
        "job_id": job_id,
        "job_name": job_name,
        "phone_missing": not bool(phone),
    }


def list_job_openings(db: Session, org_id: str, *, page: int = 1, per_page: int = 50) -> list[dict[str, Any]]:
    """List Zoho Recruit job openings for import filters."""
    token, api_domain = _ensure_access_token(db, org_id)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 200))
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"https://{api_domain}/recruit/v2/Job_Openings",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            params={"page": page, "per_page": per_page, "sort_order": "desc", "sort_by": "Created_Time"},
        )
    if res.status_code == 204:
        return []
    if res.status_code >= 400:
        raise ValueError(f"Zoho Job Openings API HTTP {res.status_code}: {(res.text or '')[:200]}")
    rows = (res.json() or {}).get("data") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        jid = str(row.get("id") or "").strip()
        if not jid:
            continue
        title = str(row.get("Job_Opening_Name") or row.get("Posting_Title") or row.get("Name") or "").strip()
        status = str(row.get("Job_Opening_Status") or row.get("Status") or "").strip()
        out.append({"id": jid, "name": title or jid, "status": status})
    return out


def list_recent_candidates(
    db: Session,
    org_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
    job_id: str | None = None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch Zoho Recruit candidates (optional job / stage filters)."""
    token, api_domain = _ensure_access_token(db, org_id)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 200))
    job = str(job_id or "").strip()
    stage_f = str(stage or "").strip()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    rows: list[Any] = []

    with httpx.Client(timeout=30.0) as client:
        if job:
            # Preferred: candidates related to a Job Opening.
            related = client.get(
                f"https://{api_domain}/recruit/v2/Job_Openings/{job}/Candidates",
                headers=headers,
                params={"page": page, "per_page": per_page},
            )
            if related.status_code == 204:
                rows = []
            elif related.status_code < 400:
                rows = (related.json() or {}).get("data") or []
            else:
                # Fallback: Applications related list, then map Candidate ids.
                apps = client.get(
                    f"https://{api_domain}/recruit/v2/Job_Openings/{job}/Applications",
                    headers=headers,
                    params={"page": page, "per_page": per_page},
                )
                if apps.status_code < 400 and apps.status_code != 204:
                    app_rows = (apps.json() or {}).get("data") or []
                    cand_ids: list[str] = []
                    for ar in app_rows:
                        if not isinstance(ar, dict):
                            continue
                        cand = ar.get("Candidate_Name") or ar.get("Candidate_ID") or ar.get("Candidate")
                        if isinstance(cand, dict) and cand.get("id"):
                            cand_ids.append(str(cand["id"]))
                        elif ar.get("id") and str(ar.get("Candidate_Name") or "").strip():
                            # Some orgs store candidate on Application itself
                            pass
                    for cid in cand_ids[:per_page]:
                        one = client.get(
                            f"https://{api_domain}/recruit/v2/Candidates/{cid}",
                            headers=headers,
                        )
                        if one.status_code < 400:
                            payload = one.json() or {}
                            data = payload.get("data")
                            if isinstance(data, list) and data:
                                rows.append(data[0])
                            elif isinstance(data, dict):
                                rows.append(data)
                elif related.status_code >= 400:
                    raise ValueError(
                        f"Zoho Job candidates API HTTP {related.status_code}: {(related.text or '')[:200]}"
                    )
        else:
            params: dict[str, Any] = {
                "page": page,
                "per_page": per_page,
                "sort_order": "desc",
                "sort_by": "Created_Time",
            }
            if stage_f:
                safe = stage_f.replace("\\", "\\\\").replace('"', '\\"')
                params["criteria"] = f'(Candidate_Status:equals:"{safe}")'
            res = client.get(
                f"https://{api_domain}/recruit/v2/Candidates",
                headers=headers,
                params=params,
            )
            if res.status_code == 204:
                rows = []
            elif res.status_code >= 400:
                raise ValueError(f"Zoho Candidates API HTTP {res.status_code}: {(res.text or '')[:200]}")
            else:
                rows = (res.json() or {}).get("data") or []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mapped = _candidate_row_from_zoho(row)
        if not mapped:
            continue
        if stage_f and mapped.get("stage") and mapped["stage"].lower() != stage_f.lower():
            continue
        if job and not mapped.get("job_id"):
            mapped["job_id"] = job
        out.append(mapped)
    return out


def _writeback_field_map(db: Session, org_id: str, partner_config: dict[str, Any] | None) -> dict[str, str]:
    """Prefer org Integrations map; fall back to Admin Partners → Zoho config."""
    org_cfg = get_recruit_config(db, org_id)
    partner_cfg = partner_config if isinstance(partner_config, dict) else load_partner_oauth_config(db)
    return {
        "score_field": str(
            org_cfg.get("score_field") or partner_cfg.get("score_field") or ""
        ).strip(),
        "status_field": str(
            org_cfg.get("status_field") or partner_cfg.get("status_field") or ""
        ).strip(),
        "report_url_field": str(
            org_cfg.get("report_url_field") or partner_cfg.get("report_url_field") or ""
        ).strip(),
    }


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
    """Push AI screening outcome onto a Zoho Recruit Candidate record (Notes always)."""
    cid = str(candidate_id or "").strip()
    if not cid:
        return {"ok": False, "detail": "No Zoho candidate id (partner_reference_id)"}

    token, api_domain = _ensure_access_token(db, org_id, partner_config=partner_config)
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
    fields = _writeback_field_map(db, org_id, partner_config)
    score_field = fields["score_field"]
    status_field = fields["status_field"]
    report_field = fields["report_url_field"]

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


def _loads_recipient_result(recipient: Any) -> dict[str, Any]:
    import json

    try:
        raw = getattr(recipient, "result_json", None)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def recipient_zoho_candidate_id(recipient: Any) -> str:
    data = _loads_recipient_result(recipient)
    return str(data.get("zoho_recruit_candidate_id") or "").strip()


def import_candidates_to_order(
    db: Session,
    org_id: str,
    *,
    order_id: str,
    candidate_ids: list[str] | None = None,
    job_id: str | None = None,
    stage: str | None = None,
    import_all_matching: bool = False,
) -> dict[str, Any]:
    """Idempotent import of Zoho Recruit candidates into an interview campaign."""
    import json
    from datetime import datetime

    from sqlalchemy import select

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.interview_intake_service import (
        _assert_interview_draft,
        _coerce_contact_phone,
        compute_intake_errors,
    )

    order = db.get(ServiceOrder, order_id)
    if order is None or str(order.org_id) != str(org_id):
        raise ValueError("Interview order not found")
    if str(order.service_code or "") != "interview":
        raise ValueError("Order is not an interview campaign")
    _assert_interview_draft(order)

    ids = [str(x).strip() for x in (candidate_ids or []) if str(x).strip()]
    job = str(job_id or "").strip() or None
    stage_f = str(stage or "").strip() or None

    listed = list_recent_candidates(db, org_id, page=1, per_page=200, job_id=job, stage=stage_f)
    by_id = {str(c["id"]): c for c in listed if c.get("id")}

    # Fetch any selected ids missing from the filtered page.
    missing_ids = [i for i in ids if i not in by_id]
    if missing_ids:
        token, api_domain = _ensure_access_token(db, org_id)
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        with httpx.Client(timeout=30.0) as client:
            for cid in missing_ids:
                res = client.get(f"https://{api_domain}/recruit/v2/Candidates/{cid}", headers=headers)
                if res.status_code >= 400:
                    continue
                payload = res.json() or {}
                data = payload.get("data")
                row = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else None
                if isinstance(row, dict):
                    mapped = _candidate_row_from_zoho(row)
                    if mapped:
                        by_id[mapped["id"]] = mapped

    if import_all_matching and not ids:
        selected = list(by_id.values())
    else:
        selected = [by_id[i] for i in ids if i in by_id]
    if not selected:
        raise ValueError("No Zoho candidates selected or matched")

    recipients = list(
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars()
    )
    existing_by_zoho: dict[str, ServiceOrderRecipient] = {}
    for r in recipients:
        zid = recipient_zoho_candidate_id(r)
        if zid:
            existing_by_zoho[zid] = r

    added = 0
    updated = 0
    skipped = 0
    missing_phone = 0

    cfg: dict[str, Any] = {}
    try:
        cfg = json.loads(order.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    if job:
        cfg["zoho_job_id"] = job
        order.config_json = json.dumps(cfg, ensure_ascii=False)

    for cand in selected:
        zid = str(cand.get("id") or "").strip()
        if not zid:
            skipped += 1
            continue
        name = str(cand.get("name") or "").strip() or "Candidate"
        phone_raw = str(cand.get("phone") or "").strip() or None
        email = str(cand.get("email") or "").strip() or None
        phone, phone_errors = _coerce_contact_phone(phone_raw)
        if not phone:
            missing_phone += 1

        match = existing_by_zoho.get(zid)
        result_meta = {
            "zoho_recruit_candidate_id": zid,
            "zoho_job_id": str(cand.get("job_id") or job or "").strip() or None,
            "zoho_stage": str(cand.get("stage") or "").strip() or None,
            "intake_source": "zoho_recruit",
        }
        if match:
            if name and (not match.name or match.name == "Unknown"):
                match.name = name
            if phone and not match.phone:
                match.phone = phone
            if email and not match.email:
                match.email = email
            merged = _loads_recipient_result(match)
            merged.update({k: v for k, v in result_meta.items() if v})
            match.result_json = json.dumps(merged, ensure_ascii=False)
            match.intake_source = "zoho_recruit"
            match.intake_errors_json = json.dumps(compute_intake_errors(match), ensure_ascii=False)
            db.add(match)
            updated += 1
            continue

        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=len(recipients) + 1,
            name=name,
            phone=phone,
            email=email,
            status="pending",
            cv_quality="missing",
            intake_source="zoho_recruit",
            intake_errors_json=json.dumps(phone_errors, ensure_ascii=False),
            result_json=json.dumps({k: v for k, v in result_meta.items() if v}, ensure_ascii=False),
        )
        recipient.intake_errors_json = json.dumps(compute_intake_errors(recipient), ensure_ascii=False)
        db.add(recipient)
        recipients.append(recipient)
        existing_by_zoho[zid] = recipient
        added += 1

    db.flush()
    recipients = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    for i, r in enumerate(recipients, start=1):
        r.row_number = i
        db.add(r)
    order.recipient_count = len(recipients)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "missing_phone": missing_phone,
        "recipient_count": order.recipient_count,
        "zoho_job_id": job,
    }


def maybe_writeback_interview_result(db: Session, *, order: Any, recipient: Any) -> dict[str, Any] | None:
    """Write Dashboard interview outcome to Zoho when recipient was imported from Recruit."""
    from app.services.partner_service import recommendation_to_status

    zid = recipient_zoho_candidate_id(recipient)
    if not zid:
        return None
    org_id = str(getattr(order, "org_id", "") or "").strip()
    if not org_id:
        return None

    parsed = _loads_recipient_result(recipient)
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    score_raw = analysis.get("score") if analysis else parsed.get("score")
    try:
        score = int(score_raw) if score_raw is not None else None
    except Exception:
        score = None
    recommendation = analysis.get("recommendation") if analysis else parsed.get("recommendation")
    result_status = recommendation_to_status(str(recommendation) if recommendation else None, score)
    report_url = (
        f"https://dashboard.voxbulk.com/interview/orders/{order.id}/recipients/{recipient.id}"
    )

    try:
        result = write_screening_result(
            db,
            org_id=org_id,
            candidate_id=zid,
            score=score,
            result_status=result_status,
            report_url=report_url,
        )
        merged = dict(parsed)
        merged["zoho_writeback"] = {
            "ok": bool(result.get("ok")),
            "at": datetime.utcnow().isoformat(),
            "result_status": result_status,
            "score": score,
        }
        import json

        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        return result
    except Exception:
        logger.exception(
            "zoho_recruit_dashboard_writeback_failed order_id=%s recipient_id=%s",
            getattr(order, "id", None),
            getattr(recipient, "id", None),
        )
        return {"ok": False, "detail": "writeback_failed"}
