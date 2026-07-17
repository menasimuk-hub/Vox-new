"""Cross-process lock for service_order_recipients.result_json read-modify-write."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_memory_locks: dict[str, Lock] = {}
_memory_guard = Lock()


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


@contextmanager
def recipient_result_lock(recipient_id: str, *, ttl_seconds: int = 30, wait_seconds: float = 8.0) -> Iterator[None]:
    """Serialize result_json updates for one recipient (Redis SET NX, memory fallback)."""
    key = f"survey:recipient_result:{recipient_id}"
    client = _redis_client()
    token = f"{time.time()}"
    acquired = False
    if client is not None:
        deadline = time.time() + max(0.2, wait_seconds)
        while time.time() < deadline:
            try:
                if client.set(key, token, nx=True, ex=max(5, int(ttl_seconds))):
                    acquired = True
                    break
            except Exception as exc:
                logger.debug("recipient_result_lock redis fallback: %s", exc)
                client = None
                break
            time.sleep(0.05)
        if acquired:
            try:
                yield
            finally:
                try:
                    if client.get(key) == token:
                        client.delete(key)
                except Exception:
                    pass
            return

    with _memory_guard:
        lock = _memory_locks.get(key)
        if lock is None:
            lock = Lock()
            _memory_locks[key] = lock
    with lock:
        yield
