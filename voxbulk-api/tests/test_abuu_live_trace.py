"""Tests for Abuu unified live trace logging."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from app.abuu import live_trace


def test_live_trace_respects_disabled_flag(caplog):
    caplog.set_level(logging.INFO)
    with patch.dict(os.environ, {"ABUU_WAITER_TRACE_ENABLED": "false"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            live_trace.live("test", phone="+972500000001", text="hello")
        finally:
            get_settings.cache_clear()
    assert not any("abuu_live_trace" in r.message for r in caplog.records)


def test_live_trace_emits_when_enabled(caplog):
    caplog.set_level(logging.INFO)
    with patch.dict(os.environ, {"ABUU_WAITER_TRACE_ENABLED": "true"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            live_trace.route(phone="+972500000001", text="دجاج", pipeline="smart")
        finally:
            get_settings.cache_clear()
    assert any("abuu_live_trace route" in r.message for r in caplog.records)


def test_outbound_sets_forbidden_hit(caplog):
    caplog.set_level(logging.INFO)
    with patch.dict(os.environ, {"ABUU_WAITER_TRACE_ENABLED": "true"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            live_trace.outbound(phone="+972500000001", reply_preview="ما لقيت أطباق لهذا الطلب")
        finally:
            get_settings.cache_clear()
    hits = [r for r in caplog.records if "abuu_live_trace out" in r.message]
    assert hits
    assert "forbidden_hit=True" in hits[0].message
