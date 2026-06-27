"""Tests for WhatsApp send rate limiting."""

from __future__ import annotations

import time
from unittest.mock import patch

from app.services.wa_send_rate_limit import acquire_whatsapp_send_slot


def test_acquire_whatsapp_send_slot_memory_fallback_paces():
    with patch("app.services.wa_send_rate_limit._redis_client", return_value=None):
        with patch("app.services.wa_send_rate_limit.get_settings") as mock_settings:
            mock_settings.return_value.wa_messages_per_second = 10.0
            t0 = time.time()
            acquire_whatsapp_send_slot(block=True)
            acquire_whatsapp_send_slot(block=True)
            elapsed = time.time() - t0
            assert elapsed >= 0.05
