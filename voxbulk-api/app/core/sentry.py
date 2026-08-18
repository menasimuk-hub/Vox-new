"""Optional Sentry. No-op when SENTRY_DSN is unset."""

from __future__ import annotations

import os
from typing import Any

_SENSITIVE_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-health-token",
    "x-api-key",
    "x-auth-token",
}
_SENSITIVE_NAME_PARTS = (
    "authorization",
    "cookie",
    "password",
    "access_token",
    "refresh_token",
    "jwt",
    "phone",
    "token",
    "secret",
)


def _dsn() -> str:
    raw = (os.getenv("SENTRY_DSN") or "").strip()
    if raw:
        return raw
    try:
        from app.core.config import get_settings

        return str(get_settings().sentry_dsn or "").strip()
    except Exception:
        return ""


def _scrub_mapping(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        kl = str(key).lower()
        if kl in _SENSITIVE_HEADER_KEYS or any(part in kl for part in _SENSITIVE_NAME_PARTS):
            out[key] = "[Filtered]"
        elif isinstance(value, dict):
            out[key] = _scrub_mapping(value)
        else:
            out[key] = value
    return out


def before_send(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Drop JWT/phone/cookies from the payload before it leaves the process."""
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_mapping(headers)
        cookies = request.get("cookies")
        if cookies:
            request["cookies"] = "[Filtered]"
        data = request.get("data")
        if isinstance(data, dict):
            request["data"] = _scrub_mapping(data)
    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = _scrub_mapping(extra)
    return event


def init_sentry() -> bool:
    """Initialise Sentry for FastAPI + Celery. Returns False when DSN is empty or SDK missing."""
    dsn = _dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        return False
    if sentry_sdk.get_client().is_active():
        return True

    env = (os.getenv("ENV") or "unknown").strip() or "unknown"
    traces = 0.05
    try:
        from app.core.config import get_settings

        settings = get_settings()
        env = str(settings.env or env)
        traces = float(getattr(settings, "sentry_traces_sample_rate", traces) or traces)
    except Exception:
        try:
            traces = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE") or traces)
        except ValueError:
            traces = 0.05

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        send_default_pii=False,
        traces_sample_rate=traces,
        before_send=before_send,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            CeleryIntegration(),
        ],
    )
    return True
