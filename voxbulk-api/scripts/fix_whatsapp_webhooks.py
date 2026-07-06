#!/usr/bin/env python3
"""Fix Telnyx messaging profile webhooks and probe Meta WhatsApp webhook verification.

Usage (VPS or local with .env + DB):
  cd voxbulk-api
  python scripts/fix_whatsapp_webhooks.py
  python scripts/fix_whatsapp_webhooks.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.core.http_ssl import httpx_ssl_verify
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService

DEFAULT_WEBHOOK_BASE = "https://api.voxbulk.com"
TELNYX_MESSAGES_PATH = "/telnyx/webhooks/messages"
META_WEBHOOK_PATH = "/webhooks/meta/whatsapp"


def _telnyx_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _list_telnyx_profiles(client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get("https://api.telnyx.com/v2/messaging_profiles", params={"page[size]": 100})
    response.raise_for_status()
    body = response.json()
    return [row for row in (body.get("data") or []) if isinstance(row, dict)]


def fix_telnyx(*, api_key: str, webhook_base: str, apply: bool) -> None:
    target = f"{webhook_base.rstrip('/')}{TELNYX_MESSAGES_PATH}"
    print(f"\n=== Telnyx messaging webhooks → {target} ===")
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), headers=_telnyx_headers(api_key)) as client:
        profiles = _list_telnyx_profiles(client)
        if not profiles:
            print("No messaging profiles found.")
            return
        for row in profiles:
            pid = str(row.get("id") or "")
            name = str(row.get("name") or "")
            current = str(row.get("webhook_url") or "").strip()
            status = "OK" if current == target else "NEEDS_UPDATE"
            print(f"  [{status}] {name} ({pid})")
            print(f"    current: {current or '(none)'}")
            if status == "NEEDS_UPDATE" and apply and pid:
                response = client.patch(
                    f"https://api.telnyx.com/v2/messaging_profiles/{pid}",
                    json={"webhook_url": target, "webhook_api_version": "2"},
                )
                response.raise_for_status()
                print(f"    updated → {target}")

        try:
            probe = httpx.get(target, timeout=15.0, verify=httpx_ssl_verify())
            print(f"\nTelnyx webhook probe GET {target} → HTTP {probe.status_code}")
        except Exception as exc:
            print(f"\nTelnyx webhook probe failed: {exc}")


def probe_meta(db) -> None:
    print(f"\n=== Meta WhatsApp webhook probe ===")
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    config = validate_meta_whatsapp_config(cfg or {})
    webhook_url = str(config.get("webhook_url") or "").strip()
    verify_token = str(config.get("webhook_verify_token") or "").strip()
    if not webhook_url:
        expected = f"{DEFAULT_WEBHOOK_BASE.rstrip('/')}{META_WEBHOOK_PATH}"
        print(f"webhook_url not configured in Admin Meta integration.")
        print(f"Expected: {expected}")
        print("Set webhook base URL in Admin → Integrations → Meta WhatsApp → Save.")
        return
    if not verify_token:
        print("webhook_verify_token missing — set in Admin → Integrations → Meta WhatsApp.")
        return
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": "voxbulk_webhook_fix_ok",
    }
    print(f"URL: {webhook_url}")
    print(f"Integration enabled: {enabled}")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, verify=httpx_ssl_verify()) as client:
            response = client.get(webhook_url, params=params)
        body = (response.text or "").strip()
        ok = response.status_code == 200 and body == "voxbulk_webhook_fix_ok"
        print(f"Probe HTTP {response.status_code} body={body[:120]!r} ok={ok}")
        if not ok:
            print(
                "Meta App Dashboard → WhatsApp → Configuration:\n"
                f"  Callback URL: {webhook_url}\n"
                f"  Verify token: (same as Admin Meta integration)\n"
                "Subscribe to: messages (and message_status if available)."
            )
    except httpx.HTTPError as exc:
        print(f"Meta webhook probe failed: {exc}")


def _telnyx_api_key(explicit: str) -> str:
    key = str(explicit or os.environ.get("TELNYX_API_KEY") or "").strip()
    if key:
        return key
    try:
        from app.core.database import get_sessionmaker
        from app.services.provider_settings import ProviderSettingsService

        db = get_sessionmaker()()
        try:
            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
            if enabled and cfg:
                return str(cfg.get("api_key") or "").strip()
        finally:
            db.close()
    except Exception as exc:
        print(f"Telnyx DB key lookup failed: {exc}")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix/probe WhatsApp webhooks on VoxBulk")
    parser.add_argument("--webhook-base", default=os.environ.get("WEBHOOK_BASE", DEFAULT_WEBHOOK_BASE))
    parser.add_argument("--apply", action="store_true", help="Patch Telnyx messaging profile webhook URLs")
    parser.add_argument("--telnyx-api-key", default="")
    args = parser.parse_args()

    _load_dotenv = ROOT / ".env"
    if _load_dotenv.is_file():
        for line in _load_dotenv.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            if key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

    api_key = _telnyx_api_key(args.telnyx_api_key)
    if api_key:
        fix_telnyx(api_key=api_key, webhook_base=args.webhook_base, apply=args.apply)
    else:
        print("TELNYX_API_KEY not set — skipping Telnyx profile scan.")

    db = get_sessionmaker()()
    try:
        probe_meta(db)
    finally:
        db.close()

    if not args.apply and api_key:
        print("\nDry-run for Telnyx. Re-run with --apply to patch profile webhook URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
