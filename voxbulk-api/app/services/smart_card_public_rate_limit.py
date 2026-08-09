"""Sliding-window rate limits for public Smart Card endpoints (IP + token)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.config import get_settings

_memory_buckets: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class SmartCardRateLimitDecision:
    allowed: bool
    retry_after_sec: int = 0


def _memory_record(key: str, *, window_sec: int, limit: int) -> SmartCardRateLimitDecision:
    now = time.time()
    bucket = _memory_buckets[key]
    while bucket and bucket[0] <= now - window_sec:
        bucket.popleft()
    if len(bucket) >= limit:
        retry = max(1, int(window_sec - (now - bucket[0])))
        return SmartCardRateLimitDecision(allowed=False, retry_after_sec=retry)
    bucket.append(now)
    return SmartCardRateLimitDecision(allowed=True)


def check_smart_card_rate_limit(
    *,
    scope: str,
    identity: str,
    limit: int,
    window_sec: int = 60,
) -> SmartCardRateLimitDecision:
    """Rate-limit by scope + identity. Uses Redis when available, else process memory."""
    lim = max(1, int(limit))
    win = max(1, int(window_sec))
    key = f"sc:rl:{scope}:{identity}"

    try:
        import redis

        settings = get_settings()
        url = str(getattr(settings, "redis_url", None) or getattr(settings, "celery_broker_url", "") or "").strip()
        if url and not url.startswith("memory://") and not url.startswith("cache+memory"):
            client = redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5)
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, time.time() - win)
            pipe.zadd(key, {str(time.time()): time.time()})
            pipe.zcard(key)
            pipe.expire(key, win + 5)
            _, _, count, _ = pipe.execute()
            if int(count or 0) > lim:
                oldest = client.zrange(key, 0, 0, withscores=True)
                retry = 5
                if oldest:
                    retry = max(1, int(win - (time.time() - float(oldest[0][1]))))
                return SmartCardRateLimitDecision(allowed=False, retry_after_sec=retry)
            return SmartCardRateLimitDecision(allowed=True)
    except Exception:
        pass

    return _memory_record(key, window_sec=win, limit=lim)
