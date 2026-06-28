"""Zoom credentials .env fallback survives empty/unreadable DB provider config."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.models.provider_config import ProviderConfig
from app.services.zoom_service import ZoomService


def test_zoom_config_uses_env_when_db_empty(monkeypatch):
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acc-env")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid-env")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec-env")
    monkeypatch.setenv("ZOOM_BASE_URL", "https://api.zoom.us/v2")
    get_settings.cache_clear()

    db = get_sessionmaker()()
    try:
        # Ensure no telnyx/zoom provider rows so the env fallback is exercised.
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
