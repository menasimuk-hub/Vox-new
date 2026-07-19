"""Platform Google Search Console OAuth for SEO Control ranking KPIs."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import get_encryptor
from app.services import site_seo_service as seo

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
STATE_PREFIX = "gsc:"
STATE_MAX_AGE_SEC = 15 * 60


def _platform_credentials(db: Session | None = None) -> tuple[str, str, str]:
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(
                db, provider="google_search_console"
            )
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
        str(getattr(settings, "google_gsc_client_id", None) or "").strip(),
        str(getattr(settings, "google_gsc_client_secret", None) or "").strip(),
        str(getattr(settings, "google_gsc_redirect_uri", None) or "").strip(),
    )


def gsc_oauth_configured(db: Session) -> bool:
    client_id, client_secret, redirect = _platform_credentials(db)
    return bool(client_id and client_secret and redirect)


def test_gsc_platform_config(db: Session) -> dict[str, Any]:
    from app.services.oauth_platform_test_service import (
        finalize_platform_test,
        mask_client_id,
        platform_credential_source,
        probe_confidential_oauth_token,
        validate_oauth_platform_fields,
    )

    client_id, client_secret, redirect = _platform_credentials(db)
    source = platform_credential_source(db, provider="google_search_console")

    checks, fields_ok = validate_oauth_platform_fields(
        client_id=client_id,
        client_secret=client_secret,
        redirect=redirect,
        provider_label="Google Search Console",
    )
    if not fields_ok:
        return finalize_platform_test(
            checks,
            ok=False,
            detail=checks[-1]["message"],
            credential_source=source,
            client_id_masked=mask_client_id(client_id),
            scopes=GSC_SCOPE,
        )

    checks.append(
        {
            "name": "credential_source",
            "status": "ok" if source == "admin_db" else "fail",
            "message": (
                "Using Admin-saved credentials"
                if source == "admin_db"
                else "Using GOOGLE_GSC_* env fallback — enable and save in Admin → Integrations"
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
            scopes=GSC_SCOPE,
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
            scopes=GSC_SCOPE,
        )

    checks.append({"name": "google_api", "status": "ok", "message": probe["detail"]})
    return finalize_platform_test(
        checks,
        ok=True,
        detail="Google Search Console OAuth app verified. Connect from SEO Control → Site Settings.",
        redirect_uri=redirect,
        credential_source=source,
        client_id_masked=mask_client_id(client_id),
        scopes=GSC_SCOPE,
    )


def _state_signing_key() -> bytes:
    # Must be deterministic across start/callback. Fernet ciphertext is random per call — do not derive from encrypt().
    settings = get_settings()
    material = (
        str(getattr(settings, "encryption_key", None) or "").strip()
        or str(getattr(settings, "jwt_secret_key", None) or "").strip()
        or "voxbulk-gsc-oauth-state"
    )
    return hashlib.sha256(f"gsc-oauth-state-v1:{material}".encode("utf-8")).digest()


def _make_state() -> str:
    ts = str(int(datetime.utcnow().timestamp()))
    nonce = secrets.token_urlsafe(12)
    body = f"{ts}.{nonce}"
    sig = hmac.new(_state_signing_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def _verify_state(state: str) -> None:
    raw = (state or "").strip()
    parts = raw.split(".")
    if len(parts) != 3:
        # Backward-compatible: accept previous Fernet-encrypted states briefly
        try:
            payload = get_encryptor().decrypt_str(raw)
        except Exception as exc:
            raise ValueError("Invalid OAuth state") from exc
        if not payload.startswith(STATE_PREFIX):
            raise ValueError("Invalid OAuth state")
        body = payload[len(STATE_PREFIX) :]
        ts_str = body.split(":", 1)[0]
        try:
            ts = int(ts_str)
        except ValueError as exc:
            raise ValueError("Invalid OAuth state") from exc
        if abs(int(datetime.utcnow().timestamp()) - ts) > STATE_MAX_AGE_SEC:
            raise ValueError("OAuth state expired — try Connect again")
        return
    ts_str, nonce, sig = parts
    body = f"{ts_str}.{nonce}"
    expected = hmac.new(_state_signing_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid OAuth state")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise ValueError("Invalid OAuth state") from exc
    if abs(int(datetime.utcnow().timestamp()) - ts) > STATE_MAX_AGE_SEC:
        raise ValueError("OAuth state expired — try Connect again")


def gsc_oauth_start(db: Session) -> str:
    client_id, client_secret, redirect = _platform_credentials(db)
    if not client_id or not client_secret or not redirect:
        raise ValueError(
            "Google Search Console OAuth is not configured. "
            "Admin → Integrations → Google Search Console (client ID, secret, redirect URI)."
        )
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": GSC_SCOPE,
        "state": _make_state(),
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _exchange_code(db: Session, code: str) -> dict[str, Any]:
    client_id, client_secret, redirect = _platform_credentials(db)
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
    data = token_res.json() or {}
    if not str(data.get("access_token") or "").strip():
        raise ValueError("Google did not return an access token")
    return data


def _refresh_access_token(db: Session, refresh_token: str) -> str:
    client_id, client_secret, _ = _platform_credentials(db)
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"GSC token refresh failed ({res.status_code})")
    access = str((res.json() or {}).get("access_token") or "").strip()
    if not access:
        raise HTTPException(status_code=400, detail="GSC token refresh returned no access token")
    return access


def _host_from_property(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw.startswith("sc-domain:"):
        return raw.split(":", 1)[1].strip()
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    return raw.split("/")[0].strip()


def _pick_property(access_token: str, preferred: str) -> str:
    preferred = (preferred or "").strip()
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(GSC_SITES_URL, headers=headers)
    if res.status_code >= 400:
        if preferred:
            return preferred
        raise ValueError(f"Could not list Search Console properties ({res.status_code})")
    entries = (res.json() or {}).get("siteEntry") or []
    urls = [str(e.get("siteUrl") or "").strip() for e in entries if e.get("siteUrl")]
    if preferred:
        if preferred in urls:
            return preferred
        # tolerate missing trailing slash on URL-prefix properties
        for u in urls:
            if u.rstrip("/") == preferred.rstrip("/"):
                return u
        # Map https://voxbulk.com -> sc-domain:voxbulk.com (or matching URL-prefix)
        host = _host_from_property(preferred)
        if host:
            domain_prop = f"sc-domain:{host}"
            if domain_prop in urls:
                return domain_prop
            www_host = host[4:] if host.startswith("www.") else f"www.{host}"
            for candidate in (f"https://{host}/", f"https://{www_host}/", f"http://{host}/"):
                if candidate in urls:
                    return candidate
        # Fall back to first property on this Google account rather than a URL Google rejects
        if urls:
            for u in urls:
                if host and host in u.lower():
                    return u
            return urls[0]
        return preferred
    for u in urls:
        if "voxbulk.com" in u.lower():
            return u
    if urls:
        return urls[0]
    raise ValueError("No Search Console properties found for this Google account")


def _query_avg_position(access_token: str, site_url: str) -> float | None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=27)
    encoded = quote(site_url, safe="")
    url = f"{GSC_SITES_URL}/{encoded}/searchAnalytics/query"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "rowLimit": 1,
    }
    with httpx.Client(timeout=45.0) as client:
        res = client.post(url, headers=headers, json=body)
    if res.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"Search Analytics query failed ({res.status_code}): {res.text[:240]}",
        )
    rows = (res.json() or {}).get("rows") or []
    if not rows:
        return None
    pos = rows[0].get("position")
    if pos is None:
        return None
    return round(float(pos), 2)


def gsc_oauth_complete(db: Session, *, code: str, state: str) -> dict[str, Any]:
    if not (code or "").strip():
        raise ValueError("Missing OAuth code")
    _verify_state(state)
    token_data = _exchange_code(db, code.strip())
    refresh = str(token_data.get("refresh_token") or "").strip()
    access = str(token_data.get("access_token") or "").strip()
    if not refresh:
        raise ValueError(
            "Google did not return a refresh token. Revoke prior access for this app in "
            "https://myaccount.google.com/permissions then Connect again."
        )

    settings = seo.ensure_settings(db)
    site_url = _pick_property(access, settings.gsc_property_url or "")
    settings.gsc_property_url = site_url
    settings.gsc_refresh_token_encrypted = seo._encrypt(refresh)
    settings.gsc_connected = True
    settings.updated_at = datetime.utcnow()
    db.commit()

    try:
        refresh_gsc_metrics(db, access_token=access)
    except Exception:
        # Connection still valid even if metrics are empty / delayed
        pass

    return {"connected": True, "gsc_property_url": site_url}


def disconnect_gsc(db: Session) -> dict[str, Any]:
    settings = seo.ensure_settings(db)
    settings.gsc_refresh_token_encrypted = None
    settings.gsc_connected = False
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": False}


def refresh_gsc_metrics(db: Session, *, access_token: str | None = None) -> dict[str, Any]:
    settings = seo.ensure_settings(db)
    refresh = seo._decrypt(settings.gsc_refresh_token_encrypted)
    if not settings.gsc_connected or not refresh:
        raise HTTPException(status_code=400, detail="Connect Google Search Console in Site Settings first.")
    site_url = (settings.gsc_property_url or "").strip()
    if not site_url:
        raise HTTPException(
            status_code=400,
            detail="Set Search Console property URL (e.g. https://voxbulk.com/ or sc-domain:voxbulk.com).",
        )
    token = access_token or _refresh_access_token(db, refresh)
    try:
        position = _query_avg_position(token, site_url)
    except HTTPException as exc:
        detail = str(exc.detail or "")
        if "403" in detail or "sufficient permission" in detail.lower():
            corrected = _pick_property(token, site_url)
            if corrected and corrected != site_url:
                site_url = corrected
                settings.gsc_property_url = site_url
                position = _query_avg_position(token, site_url)
            else:
                raise
        else:
            raise
    if position is not None:
        if settings.gsc_avg_position is not None:
            settings.gsc_avg_position_prev = settings.gsc_avg_position
        settings.gsc_avg_position = str(position)
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {
        "connected": True,
        "gsc_property_url": site_url,
        "gsc_avg_position": settings.gsc_avg_position,
        "gsc_avg_position_prev": settings.gsc_avg_position_prev,
        "note": None
        if position is not None
        else "Connected, but Search Console has no query data for the last 28 days yet.",
    }


def admin_redirect_origin() -> str:
    settings = get_settings()
    origin = str(getattr(settings, "admin_app_origin", None) or "").strip()
    if origin:
        return origin.rstrip("/")
    return "https://admin.voxbulk.com"
