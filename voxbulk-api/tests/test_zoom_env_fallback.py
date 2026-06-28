"""Zoom credentials .env fallback applies only when DB provider rows are empty."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.models.provider_config import ProviderConfig
from app.services.provider_settings import ProviderSettingsService
from app.services.zoom_service import ZoomService


def test_zoom_config_uses_env_when_db_empty(monkeypatch):
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acc-env")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid-env")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec-env")
    monkeypatch.setenv("ZOOM_BASE_URL", "https://api.zoom.us/v2")
    get_settings.cache_clear()

    db = get_sessionmaker()()
    try:
        for row in db.query(ProviderConfig).filter(ProviderConfig.provider.in_(["zoom", "telnyx"])).all():
            db.delete(row)
        db.commit()

        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "acc-env"
        assert cfg["client_id"] == "cid-env"
        assert cfg["client_secret"] == "sec-env"
        assert cfg["base_url"] == "https://api.zoom.us/v2"
    finally:
        db.close()
        get_settings.cache_clear()


def test_zoom_config_prefers_db_over_env(monkeypatch):
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acc-env")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid-env")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec-env")
    get_settings.cache_clear()

    db = get_sessionmaker()()
    try:
        ProviderSettingsService.upsert_platform_config(
            db,
            provider="zoom",
            is_enabled=True,
            config={
                "account_id": "acc-db",
                "client_id": "cid-db",
                "client_secret": "sec-db",
                "base_url": "https://api.zoom.us/v2",
            },
        )
        cfg = ZoomService._config(db)
        assert cfg["account_id"] == "acc-db"
        assert cfg["client_id"] == "cid-db"
        assert cfg["client_secret"] == "sec-db"
    finally:
        db.close()
        get_settings.cache_clear()
