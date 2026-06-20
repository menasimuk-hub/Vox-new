"""Real API probes for platform-level OAuth credentials (Admin → Integrations Test)."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.integration_test_service import _check

_HTTP_TIMEOUT_SECONDS = 10.0
_DUMMY_OAUTH_CODE = "voxbulk-platform-test-invalid-code"


def mask_client_id(client_id: str) -> str:
    cid = str(client_id or "").strip()
    if len(cid) <= 8:
        return cid[:2] + "…" if cid else "—"
    return f"{cid[:8]}…"


def platform_credential_source(db: Session | None, *, provider: str) -> str:
    if db is None:
        return "env_fallback"
    try:
        from app.services.provider_settings import ProviderSettingsService

        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=provider)
        if enabled:
            cid = str(cfg.get("client_id") or "").strip()
            secret = str(cfg.get("client_secret") or "").strip()
            redirect = str(cfg.get("redirect_uri") or "").strip()
            if cid and secret and redirect:
                return "admin_db"
    except Exception:
        pass
    return "env_fallback"


def _parse_oauth_error_body(res: httpx.Response) -> tuple[str, str, str]:
    body_text = (res.text or "")[:500]
    error = ""
    error_desc = ""
    try:
        payload = res.json()
        if isinstance(payload, dict):
            error = str(payload.get("error") or "").strip().lower()
            error_desc = str(
                payload.get("error_description") or payload.get("message") or payload.get("errorMessage") or ""
            ).strip().lower()
    except Exception:
        pass
    return body_text.lower(), error, error_desc


def probe_confidential_oauth_token(
    *,
    token_url: str,
    payload: dict[str, str],
    use_json: bool = True,
) -> dict[str, Any]:
    """Exchange a dummy auth code; valid client+secret yield invalid_grant, not client_not_found."""
    with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        if use_json:
            res = client.post(token_url, json=payload)
        else:
            res = client.post(token_url, data=payload)

    body_lower, error, error_desc = _parse_oauth_error_body(res)

    if (
        "client_not_found" in error_desc
        or "oauth client with id not found" in body_lower
        or (error == "invalid_client" and "not found" in error_desc)
        or (error == "invalid_client" and "unknown client" in error_desc)
        or (error == "unauthorized_client" and "not found" in error_desc)
    ):
        return {
            "ok": False,
            "reason": "client_not_found",
            "status_code": res.status_code,
            "detail": "OAuth client ID not recognized by the provider",
        }

    if error == "invalid_client" and (
        "invalid_client_credentials" in error_desc
        or "client authentication failed" in error_desc
        or "invalid secret" in error_desc
        or "client_secret" in error_desc
    ):
        return {
            "ok": False,
            "reason": "invalid_secret",
            "status_code": res.status_code,
            "detail": "Client ID recognized but client secret is wrong",
        }

    if error == "invalid_grant" or "code_invalid" in error_desc or "malformed auth code" in error_desc:
        return {
            "ok": True,
            "reason": "invalid_grant_expected",
            "status_code": res.status_code,
            "detail": "Provider recognized client ID and secret (dummy code rejected as expected)",
        }

    if res.status_code < 500:
        return {
            "ok": True,
            "reason": "unexpected_but_nonfatal",
            "status_code": res.status_code,
            "detail": f"Provider responded HTTP {res.status_code} — credentials likely valid",
        }

    return {
        "ok": False,
        "reason": "provider_error",
        "status_code": res.status_code,
        "detail": f"Provider error HTTP {res.status_code}",
    }


def validate_oauth_platform_fields(
    *,
    client_id: str,
    client_secret: str,
    redirect: str,
    provider_label: str,
) -> tuple[list[dict[str, Any]], bool]:
    checks: list[dict[str, Any]] = []
    if not client_id or not client_secret or not redirect:
        checks.append(
            _check(
                "credentials",
                False,
                f"{provider_label} client ID, secret, and redirect URI are required",
            )
        )
        return checks, False
    checks.append(_check("credentials", True, "Client ID, secret, and redirect URI are configured"))
    if not redirect.startswith("http"):
        checks.append(_check("redirect_uri", False, "Redirect URI must be a full https URL"))
        return checks, False
    checks.append(_check("redirect_uri", True, "Redirect URI format looks valid"))
    return checks, True


def finalize_platform_test(
    checks: list[dict[str, Any]],
    *,
    ok: bool,
    detail: str,
    redirect_uri: str = "",
    credential_source: str = "",
    client_id_masked: str = "",
    scopes: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": ok,
        "detail": detail,
        "checks": checks,
    }
    if redirect_uri:
        result["redirect_uri"] = redirect_uri
    if credential_source:
        result["credential_source"] = credential_source
    if client_id_masked:
        result["client_id_masked"] = client_id_masked
    if scopes:
        result["scopes"] = scopes
    return result
