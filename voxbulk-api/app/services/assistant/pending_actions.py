from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import get_settings


def _secret() -> bytes:
    settings = get_settings()
    raw = str(getattr(settings, "jwt_secret_key", None) or getattr(settings, "secret_key", None) or "voxbulk-assistant-dev")
    return raw.encode("utf-8")


def issue_pending_action(
    *,
    org_id: str,
    user_id: str,
    action_type: str,
    payload: dict[str, Any],
    ttl_seconds: int = 900,
) -> str:
    action_id = str(uuid.uuid4())
    body = {
        "action_id": action_id,
        "org_id": org_id,
        "user_id": user_id,
        "action_type": action_type,
        "payload": payload,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    token = json.dumps({"body": body, "sig": sig})
    return f"{action_id}:{token}"


def verify_pending_action(action_id: str, *, org_id: str, user_id: str) -> dict[str, Any] | None:
    if ":" not in action_id:
        return None
    _, token = action_id.split(":", 1)
    try:
        parsed = json.loads(token)
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
    if str(body.get("action_id")) != str(action_id).split(":", 1)[0]:
        return None
    return body
