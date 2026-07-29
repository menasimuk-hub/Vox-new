"""Phase 6: recipient upload caps + auth invite/OAuth rate limits."""

from __future__ import annotations

import io

import pytest

from app.services.auth_rate_limit import _memory_buckets, check_auth_rate_limit
from app.services.platform_catalog_service import ServiceOrderService
from app.utils.upload_limits import read_upload_capped, recipient_upload_max_bytes


@pytest.fixture(autouse=True)
def _clear_auth_rate_buckets():
    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


def test_parse_recipient_file_rejects_too_many_rows(monkeypatch):
    monkeypatch.setenv("RECIPIENT_UPLOAD_MAX_ROWS", "3")
    from app.core.config import get_settings

    get_settings.cache_clear()

    lines = ["name,phone"]
    for i in range(5):
        lines.append(f"Person {i},+44770090000{i}")
    content = ("\n".join(lines)).encode("utf-8")
    with pytest.raises(ValueError, match="Too many contacts"):
        ServiceOrderService.parse_recipient_file(content, "contacts.csv")

    get_settings.cache_clear()


def test_read_upload_capped_rejects_oversized(monkeypatch):
    import asyncio

    from fastapi import HTTPException
    from starlette.datastructures import Headers
    from starlette.datastructures import UploadFile as StarletteUploadFile

    monkeypatch.setenv("RECIPIENT_UPLOAD_MAX_MB", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()

    blob = b"x" * (1024 * 1024 + 1)
    upload = StarletteUploadFile(
        filename="big.csv",
        file=io.BytesIO(blob),
        headers=Headers({"content-type": "text/csv"}),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_upload_capped(upload))
    assert exc.value.status_code == 413
    assert recipient_upload_max_bytes() == 1024 * 1024

    get_settings.cache_clear()


def test_invite_preview_rate_limited(app_client, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MIN", "3")
    from app.core.config import get_settings

    get_settings.cache_clear()
    _memory_buckets.clear()

    # Three probes allowed, fourth returns 429 (invite not found still counts toward limit).
    for _ in range(3):
        r = app_client.get("/auth/invite-preview", params={"token": "missing-token"})
        assert r.status_code in {404, 400}
    r4 = app_client.get("/auth/invite-preview", params={"token": "missing-token"})
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers

    get_settings.cache_clear()


def test_oauth_start_rate_limited(app_client, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MIN", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    _memory_buckets.clear()

    # Provider may 400/404 when not configured; rate limit still applies by IP.
    statuses = []
    for _ in range(3):
        r = app_client.get("/auth/oauth/google/start", follow_redirects=False)
        statuses.append(r.status_code)
    assert 429 in statuses

    get_settings.cache_clear()


def test_check_auth_rate_limit_unit():
    _memory_buckets.clear()
    for _ in range(2):
        d = check_auth_rate_limit(scope="unit-test", identity="ip-1", limit=2)
        assert d.allowed is True
    d = check_auth_rate_limit(scope="unit-test", identity="ip-1", limit=2)
    assert d.allowed is False
    assert d.retry_after_sec >= 1
