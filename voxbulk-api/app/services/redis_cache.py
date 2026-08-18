"""Shared TTL cache for values that must be consistent across gunicorn workers.

Production uses Redis only. Process memory is a development fallback so local
pytest / Windows without Redis still works. A Redis outage in production is a
cache miss (recompute / re-auth) — never a silent per-worker dict.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY_PREFIX = "voxbulk:cache:"
_memory: dict[str, tuple[float, Any]] = {}


def is_production_env(env: str | None = None) -> bool:
    value = env if env is not None else get_settings().env
    return str(value or "").lower() in {"production", "prod"}


def reset_memory_cache() -> None:
    _memory.clear()


def _redis_url() -> str:
    settings = get_settings()
    return str(getattr(settings, "redis_url", None) or getattr(settings, "celery_broker_url", "") or "").strip()


def _redis_client():
    url = _redis_url()
    if not url or url.startswith("memory://") or url.startswith("cache+memory"):
        return None
    import redis

    return redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5)


def _full_key(key: str) -> str:
    return f"{KEY_PREFIX}{key}"


def _memory_get(key: str) -> Any | None:
    hit = _memory.get(key)
    if not hit:
        return None
    exp, value = hit
    if exp <= time.time():
        _memory.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: Any, ttl_sec: float) -> None:
    _memory[key] = (time.time() + max(1.0, float(ttl_sec)), value)


def cache_get(key: str) -> Any | None:
    """Return a JSON-deserialized value, or None on miss / Redis failure in production."""
    full = _full_key(key)
    try:
        client = _redis_client()
        if client is not None:
            raw = client.get(full)
            if raw is None:
                return None
            return json.loads(raw)
    except Exception:
        logger.exception("redis_cache_get_failed key=%s", key)
        if is_production_env():
            logger.critical("REDIS_CACHE_DOWN — skipping cache get (no per-worker memory)")
            return None
        return _memory_get(key)

    if is_production_env():
        logger.critical("REDIS_CACHE_NOT_CONFIGURED — skipping cache get (set REDIS_URL)")
        return None
    return _memory_get(key)


def cache_set(key: str, value: Any, ttl_sec: float) -> None:
    """Store a JSON-serializable value. No-op on production Redis failure."""
    try:
        payload = json.dumps(value, separators=(",", ":"), default=str)
    except TypeError:
        logger.exception("redis_cache_set_not_serializable key=%s", key)
        return
    ttl = max(1, int(ttl_sec))
    full = _full_key(key)
    try:
        client = _redis_client()
        if client is not None:
            client.setex(full, ttl, payload)
            return
    except Exception:
        logger.exception("redis_cache_set_failed key=%s", key)
        if is_production_env():
            logger.critical("REDIS_CACHE_DOWN — skipping cache set (no per-worker memory)")
            return
        _memory_set(key, value, ttl)
        return

    if is_production_env():
        logger.critical("REDIS_CACHE_NOT_CONFIGURED — skipping cache set (set REDIS_URL)")
        return
    _memory_set(key, value, ttl)
