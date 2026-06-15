"""Sliding-window rate limits for dashboard assistant endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from app.core.config import get_settings

_memory_buckets: dict[str, list[float]] = {}
_memory_lock = Lock()


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_sec: int = 0


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def _memory_record(key: str, *, window_sec: int, limit: int) -> RateLimitDecision:
    now = time.time()
    cutoff = now - window_sec
    with _memory_lock:
        bucket = [t for t in _memory_buckets.get(key, []) if t >= cutoff]
        if len(bucket) >= limit:
            retry = max(1, int(window_sec - (now - bucket[0])))
            _memory_buckets[key] = bucket
            return RateLimitDecision(allowed=False, retry_after_sec=retry)
        bucket.append(now)
        _memory_buckets[key] = bucket
    return RateLimitDecision(allowed=True)


def check_assistant_rate_limit(*, org_id: str, user_id: str, endpoint: str) -> RateLimitDecision:
    settings = get_settings()
    limit = max(1, int(settings.assistant_rate_limit_per_min))
    window_sec = 60
    key = f"assistant:rl:{endpoint}:{org_id}:{user_id}"

    client = _redis_client()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, time.time() - window_sec)
            pipe.zadd(key, {str(time.time()): time.time()})
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
        except Exception:
            pass

    return _memory_record(key, window_sec=window_sec, limit=limit)
