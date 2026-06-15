"""HMAC support report tokens for diagnostic assistant tickets."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import get_settings
from app.services.assistant.pending_actions import _secret

_TOKEN_TTL_SEC = 86400


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


_consumed_memory: dict[str, str] = {}


def issue_support_report_token(
    *,
    org_id: str,
    user_id: str,
    payload: dict[str, Any],
    ttl_seconds: int = _TOKEN_TTL_SEC,
) -> str:
    token_id = str(uuid.uuid4())
    body = {
        "token_id": token_id,
        "org_id": org_id,
        "user_id": user_id,
        "payload": payload,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    token = json.dumps({"body": body, "sig": sig})
    return f"{token_id}:{token}"


def verify_support_report_token(token: str, *, org_id: str, user_id: str) -> dict[str, Any] | None:
    if ":" not in token:
        return None
    token_id, blob = token.split(":", 1)
    try:
        parsed = json.loads(blob)
        body = parsed.get("body") or {}
        sig = str(parsed.get("sig") or "")
    except (json.JSONDecodeError, TypeError):
        return None

    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    expected = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    if int(body.get("exp") or 0) < int(time.time()):
        return None
    if str(body.get("org_id")) != str(org_id) or str(body.get("user_id")) != str(user_id):
        return None
    if str(body.get("token_id")) != str(token_id):
        return None
    return body


def _consume_key(token_id: str) -> str:
    return f"assistant:report:{token_id}"


def mark_report_token_consumed(token_id: str, *, ticket_ref: str) -> None:
    key = _consume_key(token_id)
    client = _redis_client()
    if client is not None:
        try:
            client.setex(key, _TOKEN_TTL_SEC, ticket_ref)
            return
        except Exception:
            pass
    _consumed_memory[key] = ticket_ref


def get_consumed_ticket_ref(token_id: str) -> str | None:
    key = _consume_key(token_id)
    client = _redis_client()
    if client is not None:
        try:
            val = client.get(key)
            if val:
                return str(val)
        except Exception:
            pass
    return _consumed_memory.get(key)
