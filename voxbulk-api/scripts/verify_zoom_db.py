#!/usr/bin/env python3
"""VPS diagnostic: confirm Zoom OAuth credentials are stored and decryptable in DB.

Usage (on VPS after saving Zoom in admin):
    cd /www/voxbulk/voxbulk-api
    source .venv/bin/activate
    python scripts/verify_zoom_db.py

Never prints client_secret — only secret_set boolean and non-secret fields.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.database import get_sessionmaker
from app.services.provider_settings import ProviderSettingsService
from app.services.zoom_service import ZoomService


def _row_meta(db, provider: str) -> dict:
    row = db.execute(
        text(
            "SELECT provider, is_enabled, updated_at, LENGTH(encrypted_json) AS cipher_len "
            "FROM provider_configs WHERE scope='platform' AND org_id IS NULL AND provider=:p"
        ),
        {"p": provider},
    ).mappings().first()
    return dict(row) if row else {}


def main() -> int:
    db = get_sessionmaker()()
    try:
        print("=== provider_configs rows (zoom / telnyx) ===")
        for provider in ("zoom", "telnyx"):
            meta = _row_meta(db, provider)
            print(json.dumps({"provider": provider, **meta}, default=str))

        print("\n=== decrypted probe (secrets redacted) ===")
        zoom_cfg, zoom_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
        telnyx_cfg, telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        zoom_cfg = zoom_cfg or {}
        telnyx_cfg = telnyx_cfg or {}

        print(json.dumps({
            "zoom": {
                "is_enabled": zoom_enabled,
                "account_id": str(zoom_cfg.get("account_id") or ""),
                "client_id": str(zoom_cfg.get("client_id") or ""),
                "base_url": str(zoom_cfg.get("base_url") or ""),
                "secret_set": bool(str(zoom_cfg.get("client_secret") or "").strip()),
                "zoom_oauth_updated_at": str(zoom_cfg.get("zoom_oauth_updated_at") or ""),
            },
            "telnyx_zoom": {
                "is_enabled": telnyx_enabled,
                "zoom_account_id": str(telnyx_cfg.get("zoom_account_id") or ""),
                "zoom_client_id": str(telnyx_cfg.get("zoom_client_id") or ""),
                "zoom_base_url": str(telnyx_cfg.get("zoom_base_url") or ""),
                "secret_set": bool(str(telnyx_cfg.get("zoom_client_secret") or "").strip()),
                "zoom_oauth_updated_at": str(telnyx_cfg.get("zoom_oauth_updated_at") or ""),
            },
        }, indent=2))

        print("\n=== ZoomService._config (runtime resolver) ===")
        try:
            resolved = ZoomService._config(db)
            print(json.dumps({
                "account_id": resolved["account_id"],
                "client_id": resolved["client_id"],
                "base_url": resolved["base_url"],
                "secret_set": bool(resolved.get("client_secret")),
            }, indent=2))
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            return 1

        ProviderSettingsService.verify_zoom_oauth_persisted(db)
        print("\nverify_zoom_oauth_persisted: OK")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
