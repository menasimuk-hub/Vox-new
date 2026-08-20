"""Cross-process rate limiting for WhatsApp outbound sends via Telnyx."""

from __future__ import annotations

import logging
import time
from threading import Lock

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_memory_lock = Lock()
_memory_last_sent_at = 0.0


class WhatsAppOrgRateLimitExceeded(ValueError):
    """Raised when an org exceeds its hourly/daily WhatsApp cap."""


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def _enforce_org_caps(client, *, org_id: str, now: float, per_org_hour: int, per_org_day: int) -> None:
    hour_bucket = time.strftime("%Y%m%d%H", time.gmtime(now))
    day_bucket = time.strftime("%Y%m%d", time.gmtime(now))
    hour_key = f"wa:send:org:{org_id}:hour:{hour_bucket}"
    day_key = f"wa:send:org:{org_id}:day:{day_bucket}"
    hour_count = int(client.incr(hour_key))
    if hour_count == 1:
        client.expire(hour_key, 3605)
    if hour_count > per_org_hour:
        raise WhatsAppOrgRateLimitExceeded(f"Org WhatsApp hourly cap reached ({per_org_hour}/hour)")
    day_count = int(client.incr(day_key))
    if day_count == 1:
        client.expire(day_key, 86405)
    if day_count > per_org_day:
        raise WhatsAppOrgRateLimitExceeded(f"Org WhatsApp daily cap reached ({per_org_day}/day)")


def acquire_whatsapp_send_slot(*, block: bool = True, org_id: str | None = None) -> None:
    """Block until a WhatsApp send slot is available (global platform limit)."""
    settings = get_settings()
    per_sec = max(0.5, float(getattr(settings, "wa_messages_per_second", 8.0) or 8.0))
    limit = max(1, int(per_sec))
    min_interval = 1.0 / float(limit)
    per_org_hour = max(1, int(getattr(settings, "wa_messages_per_org_per_hour", 250) or 250))
    per_org_day = max(1, int(getattr(settings, "wa_messages_per_org_per_day", 2000) or 2000))

    client = _redis_client()
    if client is not None:
        while True:
            now = time.time()
            bucket = int(now)
            key = f"wa:send:sec:{bucket}"
            try:
                clean_org_id = str(org_id or "").strip()
                if clean_org_id:
                    _enforce_org_caps(
                        client,
                        org_id=clean_org_id,
                        now=now,
                        per_org_hour=per_org_hour,
                        per_org_day=per_org_day,
                    )
                count = int(client.incr(key))
                if count == 1:
                    client.expire(key, 2)
                if count <= limit:
                    return
                if not block:
                    return
                sleep_for = max(0.01, 1.0 - (now - bucket))
                time.sleep(sleep_for)
                continue
            except Exception as exc:
                logger.debug("wa_send_rate_limit redis fallback: %s", exc)
                break

    global _memory_last_sent_at
    with _memory_lock:
        now = time.time()
        wait = min_interval - (now - _memory_last_sent_at)
        if wait > 0:
            time.sleep(wait)
        _memory_last_sent_at = time.time()
