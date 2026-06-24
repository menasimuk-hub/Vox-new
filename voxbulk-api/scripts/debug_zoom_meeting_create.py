#!/usr/bin/env python3
"""Diagnose Zoom token/user/meeting calls using VoxBulk admin-stored config.

Usage:
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/debug_zoom_meeting_create.py
  .venv/bin/python scripts/debug_zoom_meeting_create.py --topic "VoxBulk Debug Meeting"
  .venv/bin/python scripts/debug_zoom_meeting_create.py --skip-create
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.provider_settings import ProviderSettingsService

TOKEN_URL = "https://zoom.us/oauth/token"


def _mask(value: str, *, keep_start: int = 4, keep_end: int = 4) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "<empty>"
    if len(raw) <= keep_start + keep_end:
        return "*" * len(raw)
    return f"{raw[:keep_start]}...{raw[-keep_end:]}"


def _parse_json(text: str) -> Any:
    body = str(text or "").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except Exception:
        return body


def _resolve_zoom_config(db) -> tuple[dict[str, str], dict[str, str]]:
    """Mirror app.services.zoom_service.ZoomService._config with source metadata."""
    zoom_cfg, zoom_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
    telnyx_cfg, telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    zoom_cfg = zoom_cfg or {}
    telnyx_cfg = telnyx_cfg or {}

    account_id = str(zoom_cfg.get("account_id") or "").strip()
    client_id = str(zoom_cfg.get("client_id") or "").strip()
    client_secret = str(zoom_cfg.get("client_secret") or "").strip()
    base_url = str(zoom_cfg.get("base_url") or "https://api.zoom.us/v2").strip().rstrip("/")

    source = {
        "account_id": "zoom",
        "client_id": "zoom",
        "client_secret": "zoom",
        "base_url": "zoom",
    }

    zoom_complete = bool(account_id and client_id and client_secret)
    telnyx_account_id = str(telnyx_cfg.get("zoom_account_id") or "").strip()
    telnyx_client_id = str(telnyx_cfg.get("zoom_client_id") or "").strip()
    telnyx_client_secret = str(telnyx_cfg.get("zoom_client_secret") or "").strip()
    telnyx_base_url = str(telnyx_cfg.get("zoom_base_url") or "").strip().rstrip("/")
    telnyx_complete = bool(telnyx_account_id and telnyx_client_id and telnyx_client_secret)

    if telnyx_enabled and telnyx_complete:
        use_telnyx = False
        if not zoom_enabled or not zoom_complete:
            use_telnyx = True
        else:
            zoom_obj = ProviderSettingsService.get_platform_config(db, provider="zoom")
            telnyx_obj = ProviderSettingsService.get_platform_config(db, provider="telnyx")
            zoom_updated = getattr(zoom_obj, "updated_at", None)
            telnyx_updated = getattr(telnyx_obj, "updated_at", None)
            if zoom_updated is not None and telnyx_updated is not None and telnyx_updated > zoom_updated:
                use_telnyx = True
        if use_telnyx:
            account_id = telnyx_account_id
            client_id = telnyx_client_id
            client_secret = telnyx_client_secret
            base_url = telnyx_base_url or base_url or "https://api.zoom.us/v2"
            source["account_id"] = "telnyx.zoom_account_id"
            source["client_id"] = "telnyx.zoom_client_id"
            source["client_secret"] = "telnyx.zoom_client_secret"
            source["base_url"] = "telnyx.zoom_base_url" if telnyx_base_url else source["base_url"]
    elif telnyx_enabled and (not zoom_enabled or not zoom_complete):
        if not account_id and telnyx_account_id:
            account_id = telnyx_account_id
            source["account_id"] = "telnyx.zoom_account_id"
        if not client_id and telnyx_client_id:
            client_id = telnyx_client_id
            source["client_id"] = "telnyx.zoom_client_id"
        if not client_secret and telnyx_client_secret:
            client_secret = telnyx_client_secret
            source["client_secret"] = "telnyx.zoom_client_secret"
        if telnyx_base_url:
            base_url = telnyx_base_url
            source["base_url"] = "telnyx.zoom_base_url"

    cfg = {
        "account_id": account_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "base_url": base_url or "https://api.zoom.us/v2",
    }
    return cfg, source


def _resolve_telnyx_zoom_only_config(db) -> dict[str, str] | None:
    telnyx_cfg, telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not telnyx_enabled:
        return None
    telnyx_cfg = telnyx_cfg or {}
    account_id = str(telnyx_cfg.get("zoom_account_id") or "").strip()
    client_id = str(telnyx_cfg.get("zoom_client_id") or "").strip()
    client_secret = str(telnyx_cfg.get("zoom_client_secret") or "").strip()
    if not account_id or not client_id or not client_secret:
        return None
    base_url = str(telnyx_cfg.get("zoom_base_url") or "https://api.zoom.us/v2").strip().rstrip("/")
    return {
        "account_id": account_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "base_url": base_url or "https://api.zoom.us/v2",
    }


def _is_invalid_client(response: httpx.Response) -> bool:
    body = _parse_json(response.text)
    if isinstance(body, dict):
        err = str(body.get("error") or "").strip().lower()
        reason = str(body.get("reason") or body.get("error_description") or "").strip().lower()
        if err == "invalid_client" or "invalid client" in reason:
            return True
    return "invalid client" in str(response.text or "").lower()


def _print_http_result(label: str, response: httpx.Response) -> None:
    parsed = _parse_json(response.text)
    print(f"\n[{label}] status={response.status_code}")
    if isinstance(parsed, dict):
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    elif isinstance(parsed, list):
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    else:
        print(str(parsed or "<empty body>"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Zoom meeting creation with stored admin config")
    parser.add_argument("--topic", default="VoxBulk Zoom debug meeting", help="Meeting topic to create")
    parser.add_argument("--duration", type=int, default=30, help="Meeting duration in minutes")
    parser.add_argument("--skip-create", action="store_true", help="Only test token + /users/me, do not create meeting")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        cfg, source = _resolve_zoom_config(db)
        telnyx_only_cfg = _resolve_telnyx_zoom_only_config(db)

    print("=== VoxBulk Zoom Config Resolver ===")
    print(f"account_id: {_mask(cfg['account_id'])} (source: {source['account_id']})")
    print(f"client_id: {_mask(cfg['client_id'])} (source: {source['client_id']})")
    print(f"client_secret: {_mask(cfg['client_secret'])} (source: {source['client_secret']})")
    print(f"base_url: {cfg['base_url']} (source: {source['base_url']})")
    if telnyx_only_cfg:
        print("\nTelnyx Zoom-only credentials detected:")
        print(f"account_id: {_mask(telnyx_only_cfg['account_id'])}")
        print(f"client_id: {_mask(telnyx_only_cfg['client_id'])}")
        print(f"client_secret: {_mask(telnyx_only_cfg['client_secret'])}")
        print(f"base_url: {telnyx_only_cfg['base_url']}")

    missing = [k for k in ("account_id", "client_id", "client_secret") if not cfg.get(k)]
    if missing:
        print(f"\nERROR: missing required config values: {', '.join(missing)}")
        print("Fill Admin -> Integrations -> Zoom OR Telnyx Zoom fields, then rerun.")
        return 1

    auth = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    token_url = f"{TOKEN_URL}?grant_type=account_credentials&account_id={cfg['account_id']}"

    try:
        with httpx.Client(timeout=30.0) as client:
            token_res = client.post(token_url, headers={"Authorization": f"Basic {auth}"})
            _print_http_result("TOKEN", token_res)
            active_cfg = cfg
            if token_res.status_code >= 400:
                can_fallback = bool(telnyx_only_cfg)
                same_creds = False
                if telnyx_only_cfg:
                    same_creds = (
                        telnyx_only_cfg["account_id"] == cfg["account_id"]
                        and telnyx_only_cfg["client_id"] == cfg["client_id"]
                        and telnyx_only_cfg["client_secret"] == cfg["client_secret"]
                    )
                if can_fallback and not same_creds and _is_invalid_client(token_res):
                    print("\nPrimary token failed with invalid_client. Retrying with telnyx.zoom_* credentials ...")
                    fallback_auth = base64.b64encode(
                        f"{telnyx_only_cfg['client_id']}:{telnyx_only_cfg['client_secret']}".encode()
                    ).decode()
                    fallback_token_url = (
                        f"{TOKEN_URL}?grant_type=account_credentials&account_id={telnyx_only_cfg['account_id']}"
                    )
                    fallback_res = client.post(
                        fallback_token_url,
                        headers={"Authorization": f"Basic {fallback_auth}"},
                    )
                    _print_http_result("TOKEN_FALLBACK_TELNYX", fallback_res)
                    token_res = fallback_res
                    if token_res.status_code < 400:
                        active_cfg = telnyx_only_cfg
                if token_res.status_code >= 400:
                    print("\nFAIL: token request failed, cannot continue.")
                    return 2

            token_data = _parse_json(token_res.text)
            if not isinstance(token_data, dict):
                print("\nFAIL: token response is not JSON object.")
                return 2

            token = str(token_data.get("access_token") or "").strip()
            scope_raw = str(token_data.get("scope") or "").strip()
            scope_list = [s for s in scope_raw.split() if s]
            print("\nResolved token scopes:")
            if scope_list:
                for s in scope_list:
                    print(f" - {s}")
            else:
                print(" - <none reported>")

            if not token:
                print("\nFAIL: token response missing access_token.")
                return 2

            user_res = client.get(
                f"{active_cfg['base_url']}/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            _print_http_result("USERS_ME", user_res)
            if user_res.status_code >= 400:
                print("\nFAIL: /users/me failed. Meeting creation likely fails too.")
                return 3

            if args.skip_create:
                print("\nPASS: token + /users/me succeeded (meeting creation skipped).")
                return 0

            payload = {
                "topic": str(args.topic).strip() or "VoxBulk Zoom debug meeting",
                "type": 2,
                "duration": max(int(args.duration or 30), 15),
                "settings": {
                    "join_before_host": True,
                    "waiting_room": False,
                    "auto_recording": "cloud",
                },
            }
            print("\nMeeting create payload:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            create_res = client.post(
                f"{active_cfg['base_url']}/users/me/meetings",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            _print_http_result("CREATE_MEETING", create_res)
            if create_res.status_code >= 400:
                print("\nFAIL: meeting creation failed. Check error body above for missing scope/license/account issues.")
                return 4

            created = _parse_json(create_res.text)
            meeting_id = created.get("id") if isinstance(created, dict) else None
            join_url = created.get("join_url") if isinstance(created, dict) else None
            print("\nPASS: meeting created successfully.")
            print(f"meeting_id={meeting_id}")
            print(f"join_url={join_url}")
            return 0
    except Exception as exc:
        print(f"\nFAIL: unexpected exception: {exc}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
