"""Expo visitor summary: one email per visitor per exhibition."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.workers.expo_summary_tasks import _lead_local_date, _visitor_summary_already_sent


def test_lead_local_date_uses_exhibition_tz():
    # 2026-08-12 23:30 UTC → 2026-08-13 in London (BST)
    created = datetime(2026, 8, 12, 23, 30, 0)
    assert _lead_local_date(created, ZoneInfo("Europe/London")) == date(2026, 8, 13)


def test_lead_local_date_none():
    assert _lead_local_date(None, ZoneInfo("Europe/London")) is None


def test_already_sent_ignores_summary_date():
    class _Result:
        def scalar_one_or_none(self):
            return "row-id"

    class _Db:
        def execute(self, *_a, **_k):
            return _Result()

    assert _visitor_summary_already_sent(
        _Db(), exhibition_id="ex-1", visitor_email="daddyservicesltd@gmail.com"
    ) is True


def test_not_already_sent():
    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        def execute(self, *_a, **_k):
            return _Result()

    assert _visitor_summary_already_sent(
        _Db(), exhibition_id="ex-1", visitor_email="other@example.com"
    ) is False
