"""Simple sliding-window rate limits for auth endpoints (login/register/reset)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.config import get_settings

_memory_buckets: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class AuthRateLimitDecision:
    allowed: bool
    retry_after_sec: int = 0


def _memory_record(key: str, *, window_sec: int, limit: int) -> AuthRateLimitDecision:
    now = time.time()
    bucket = _memory_buckets[key]
    while bucket and bucket[0] <= now - window_sec:
        bucket.popleft()
    if len(bucket) >= limit:
        retry = max(1, int(window_sec - (now - bucket[0])))
        return AuthRateLimitDecision(allowed=False, retry_after_sec=retry)
    bucket.append(now)
    return AuthRateLimitDecision(allowed=True)


def check_auth_rate_limit(*, scope: str, identity: str, limit: int | None = None) -> AuthRateLimitDecision:
    """
    Rate-limit auth actions by scope + identity (IP and/or email).

    Defaults: 20 attempts / 60s (configurable via AUTH_RATE_LIMIT_PER_MIN).
    """
    settings = get_settings()
    lim = max(1, int(limit if limit is not None else getattr(settings, "auth_rate_limit_per_min", 20) or 20))
    window_sec = 60
    key = f"auth:rl:{scope}:{identity}"

    try:
        import redis

        url = str(getattr(settings, "redis_url", None) or getattr(settings, "celery_broker_url", "") or "").strip()
        if url and not url.startswith("memory://") and not url.startswith("cache+memory"):
            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5)
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, time.time() - window_sec)
            pipe.zadd(key, {str(time.time()): time.time()})
            pipe.zcard(key)
            pipe.expire(key, window_sec + 5)
            _, _, count, _ = pipe.execute()
            if int(count or 0) > lim:
                oldest = client.zrange(key, 0, 0, withscores=True)
                retry = 5
                if oldest:
                    retry = max(1, int(window_sec - (time.time() - float(oldest[0][1]))))
                return AuthRateLimitDecision(allowed=False, retry_after_sec=retry)
            return AuthRateLimitDecision(allowed=True)
    except Exception:
        pass

    return _memory_record(key, window_sec=window_sec, limit=lim)
