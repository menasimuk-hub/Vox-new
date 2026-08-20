"""Tests for WhatsApp send rate limiting."""

from __future__ import annotations

import time
from unittest.mock import patch

from app.services.wa_send_rate_limit import WhatsAppOrgRateLimitExceeded, _enforce_org_caps, acquire_whatsapp_send_slot


def test_acquire_whatsapp_send_slot_memory_fallback_paces():
    with patch("app.services.wa_send_rate_limit._redis_client", return_value=None):
        with patch("app.services.wa_send_rate_limit.get_settings") as mock_settings:
            mock_settings.return_value.wa_messages_per_second = 10.0
            t0 = time.time()
            acquire_whatsapp_send_slot(block=True)
            acquire_whatsapp_send_slot(block=True)
            elapsed = time.time() - t0
            assert elapsed >= 0.05


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = int(self.counts.get(key, 0)) + 1
        return self.counts[key]

    def expire(self, key: str, ttl: int) -> None:
        self.expiries[key] = ttl


def test_org_caps_raise_after_limit():
    client = _FakeRedis()
    now = 1_725_000_000.0
    _enforce_org_caps(client, org_id="org-1", now=now, per_org_hour=2, per_org_day=5)
    _enforce_org_caps(client, org_id="org-1", now=now, per_org_hour=2, per_org_day=5)
    try:
        _enforce_org_caps(client, org_id="org-1", now=now, per_org_hour=2, per_org_day=5)
        assert False, "expected WhatsAppOrgRateLimitExceeded"
    except WhatsAppOrgRateLimitExceeded as exc:
        assert "hourly cap" in str(exc)
