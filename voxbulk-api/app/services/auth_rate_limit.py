"""Simple sliding-window rate limits for auth endpoints (login/register/reset)."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.sliding_window_rate_limit import (
    RateLimitDecision as AuthRateLimitDecision,
    _memory_buckets,
    check_sliding_window,
)

__all__ = ["AuthRateLimitDecision", "_memory_buckets", "check_auth_rate_limit"]


def check_auth_rate_limit(*, scope: str, identity: str, limit: int | None = None) -> AuthRateLimitDecision:
    """
    Rate-limit auth actions by scope + identity (IP and/or email).

    Defaults: 20 attempts / 60s (configurable via AUTH_RATE_LIMIT_PER_MIN).
    Production uses Redis only (no silent per-worker memory bucket).
    """
    settings = get_settings()
    lim = max(1, int(limit if limit is not None else getattr(settings, "auth_rate_limit_per_min", 20) or 20))
    key = f"auth:rl:{scope}:{identity}"
    return check_sliding_window(key=key, limit=lim, window_sec=60, log_name="auth_rate_limit")
