"""Cross-process rate limiting for WhatsApp outbound sends via Telnyx."""

from __future__ import annotations

import logging
import time
from threading import Lock

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_memory_lock = Lock()
_memory_last_sent_at = 0.0


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def acquire_whatsapp_send_slot(*, block: bool = True) -> None:
    """Block until a WhatsApp send slot is available (global platform limit)."""
    settings = get_settings()
    per_sec = max(0.5, float(getattr(settings, "wa_messages_per_second", 8.0) or 8.0))
    limit = max(1, int(per_sec))
    min_interval = 1.0 / float(limit)

    client = _redis_client()
    if client is not None:
        while True:
            now = time.time()
            bucket = int(now)
            key = f"wa:send:sec:{bucket}"
            try:
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
