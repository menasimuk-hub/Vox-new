"""HttpOnly session cookie for dashboard / public / admin browser logins.

The JWT is not readable by JavaScript. API clients (pytest, scripts) still receive
`access_token` in JSON when the request has no browser Origin header.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core.config import get_settings
from app.core.cors_utils import is_cors_origin_allowed

SESSION_COOKIE_NAME = "voxbulk_session"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def cookie_secure(request: Request) -> bool:
    settings = get_settings()
    if str(settings.env or "").lower() in {"production", "prod", "staging"}:
        return True
    try:
        if str(request.url.scheme or "").lower() == "https":
            return True
        xf = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        return xf == "https"
    except Exception:
        return False


def session_cookie_max_age() -> int:
    minutes = int(get_settings().access_token_expire_minutes or 1440)
    return max(60, minutes * 60)


def include_access_token_in_json(request: Request) -> bool:
    """Browsers send Origin — omit the JWT so XSS cannot read it from the login response."""
    return not bool((request.headers.get("origin") or "").strip())


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    raw = str(token or "").strip()
    if not raw:
        return
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=session_cookie_max_age(),
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
    )


def read_session_cookie(request: Request) -> str:
    try:
        return str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    except Exception:
        return ""


def assert_csrf_for_cookie_auth(request: Request) -> None:
    """Cookie-authenticated mutations must come from an allowed frontend Origin."""
    if str(request.method or "GET").upper() in _SAFE_METHODS:
        return
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return
    if is_cors_origin_allowed(origin, get_settings()):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cross-site request blocked",
    )


def session_json_response(
    request: Request,
    *,
    token: str,
    org_id: str,
    user_id: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "ok": True,
        "token_type": "bearer",
        "org_id": org_id,
        "user_id": user_id,
    }
    if extra:
        body.update(extra)
    if include_access_token_in_json(request):
        body["access_token"] = token
    res = JSONResponse(body)
    set_session_cookie(res, request, token)
    return res
