"""Single-owner lock for background scheduler loops.

The API is served by multiple uvicorn workers, and every worker starts the same
asyncio scheduler loops (interview/survey call dispatch, reminders, mailbox sync,
ATS, retention, weekly digest). Without coordination each tick would run N times,
which can double-dial candidates (extra Telnyx charges) and duplicate outbound
email/WhatsApp.

This module implements a lightweight Redis leader election so only ONE worker
process performs scheduler work at a time. The leader holds a short-lived key and
refreshes it every tick; if the leader dies, the key expires and another worker
takes over within ``LEADER_TTL_SECONDS``.

Fail-open: if Redis is unreachable we allow the tick to run rather than silently
halting all dispatch (availability over the small risk of duplication during a
Redis outage).
"""

from __future__ import annotations

import logging
import os
import socket

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LEADER_KEY = "voxbulk:scheduler:leader"
# Ticks run roughly every 30s; the TTL must comfortably outlast one tick so a
# slow tick does not drop leadership mid-work, but be short enough that a dead
# leader is replaced quickly.
LEADER_TTL_SECONDS = 90

_OWNER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def is_scheduler_leader(*, ttl: int = LEADER_TTL_SECONDS) -> bool:
    """Return True if this worker process owns the scheduler leadership this tick.

    Returns True when Redis is unavailable (fail-open) so scheduled work still runs
    on single-node / Redis-down setups.
    """
    client = _redis_client()
    if client is None:
        return True
    try:
        # Take leadership if nobody holds it.
        if client.set(LEADER_KEY, _OWNER_ID, nx=True, ex=ttl):
            return True
        current = client.get(LEADER_KEY)
        if current == _OWNER_ID:
            # We are the existing leader — refresh the lease.
            client.expire(LEADER_KEY, ttl)
            return True
        return False
    except Exception as exc:
        logger.debug("scheduler_leader redis fallback: %s", exc)
        return True
