"""Sliding-window rate limits for public Smart Card endpoints (IP + token)."""

from __future__ import annotations

from app.services.sliding_window_rate_limit import (
    RateLimitDecision as SmartCardRateLimitDecision,
    _memory_buckets,
    check_sliding_window,
)

__all__ = ["SmartCardRateLimitDecision", "_memory_buckets", "check_smart_card_rate_limit"]


def check_smart_card_rate_limit(
    *,
    scope: str,
    identity: str,
    limit: int,
    window_sec: int = 60,
) -> SmartCardRateLimitDecision:
    """Rate-limit by scope + identity. Redis in production; process memory in dev/test."""
    key = f"sc:rl:{scope}:{identity}"
    return check_sliding_window(
        key=key,
        limit=max(1, int(limit)),
        window_sec=max(1, int(window_sec)),
        log_name="smart_card_rate_limit",
    )
