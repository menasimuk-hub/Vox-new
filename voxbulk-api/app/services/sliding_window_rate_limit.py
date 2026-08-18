"""Sliding-window counters shared by auth and Smart Card rate limits."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_memory_buckets: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_sec: int = 0


def is_production_env(env: str | None = None) -> bool:
    value = env if env is not None else get_settings().env
    return str(value or "").lower() in {"production", "prod"}


def _memory_record(key: str, *, window_sec: int, limit: int) -> RateLimitDecision:
    now = time.time()
    bucket = _memory_buckets[key]
    while bucket and bucket[0] <= now - window_sec:
        bucket.popleft()
    if len(bucket) >= limit:
        retry = max(1, int(window_sec - (now - bucket[0])))
        return RateLimitDecision(allowed=False, retry_after_sec=retry)
    bucket.append(now)
    return RateLimitDecision(allowed=True)


def _redis_url() -> str:
    settings = get_settings()
    return str(getattr(settings, "redis_url", None) or getattr(settings, "celery_broker_url", "") or "").strip()


def _try_redis(key: str, *, window_sec: int, limit: int) -> RateLimitDecision | None:
    """Return a decision when Redis is usable; None when Redis is not configured."""
    url = _redis_url()
    if not url or url.startswith("memory://") or url.startswith("cache+memory"):
        return None
    import redis

    client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5)
    pipe = client.pipeline()
    now = time.time()
    pipe.zremrangebyscore(key, 0, now - window_sec)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window_sec + 5)
    _, _, count, _ = pipe.execute()
    if int(count or 0) > limit:
        oldest = client.zrange(key, 0, 0, withscores=True)
        retry = 5
        if oldest:
            retry = max(1, int(window_sec - (time.time() - float(oldest[0][1]))))
        return RateLimitDecision(allowed=False, retry_after_sec=retry)
    return RateLimitDecision(allowed=True)


def check_sliding_window(
    *,
    key: str,
    limit: int,
    window_sec: int,
    log_name: str,
) -> RateLimitDecision:
    """
    Redis when configured. Production never uses a silent per-worker memory bucket:
    Redis failure is logged at CRITICAL and the request is allowed (fail open) so
    login/Smart Card stay up. Non-production falls back to process memory.
    """
    lim = max(1, int(limit))
    win = max(1, int(window_sec))
    try:
        decision = _try_redis(key, window_sec=win, limit=lim)
        if decision is not None:
            return decision
    except Exception:
        logger.exception("%s_redis_unavailable", log_name)
        if is_production_env():
            logger.critical(
                "%s_REDIS_DOWN — failing open (no per-worker memory bucket)",
                log_name.upper(),
            )
            return RateLimitDecision(allowed=True)
        return _memory_record(key, window_sec=win, limit=lim)

    if is_production_env():
        logger.critical(
            "%s_REDIS_NOT_CONFIGURED — failing open (set REDIS_URL)",
            log_name.upper(),
        )
        return RateLimitDecision(allowed=True)
    return _memory_record(key, window_sec=win, limit=lim)
