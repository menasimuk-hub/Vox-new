from __future__ import annotations

import re

from fastapi import Request
from starlette.responses import Response

from app.core.config import Settings


def is_cors_origin_allowed(origin: str | None, settings: Settings) -> bool:
    if not origin:
        return False
    if origin in settings.cors_allow_origins:
        return True
    regex = settings.cors_allow_origin_regex
    if regex and re.fullmatch(regex, origin):
        return True
    return False


def apply_cors_headers(request: Request, response: Response, settings: Settings) -> Response:
    """Ensure cross-origin dashboard requests always receive ACAO on error responses."""
    origin = request.headers.get("origin")
    if not origin or not is_cors_origin_allowed(origin, settings):
        return response
    if "access-control-allow-origin" not in response.headers:
        response.headers["Access-Control-Allow-Origin"] = origin
    if settings.cors_allow_credentials:
        response.headers.setdefault("Access-Control-Allow-Credentials", "true")
    response.headers.setdefault("Vary", "Origin")
    return response
