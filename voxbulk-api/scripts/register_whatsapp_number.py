#!/usr/bin/env python3
"""Re-register a Meta WhatsApp Cloud API phone number (manual ops).

Default action: POST /{phone_number_id}/register with two-step verification PIN.

Usage:
  cd voxbulk-api
  python scripts/register_whatsapp_number.py
  python scripts/register_whatsapp_number.py --request-code
  python scripts/register_whatsapp_number.py --verify-code 123456

Reads META_* vars from voxbulk-api/.env (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PHONE = "+447822002099"
DEFAULT_GRAPH_VERSION = "v25.0"

# Meta error hints for PIN / verification flows
_PIN_ERROR_MARKERS = (
    "pin",
    "two step",
    "two-step",
    "verification",
    "133005",
    "133006",
    "133008",
    "100",
)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _config_from_db() -> dict[str, str] | None:
    try:
        from app.core.database import get_sessionmaker
        from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
        from app.services.provider_settings import ProviderSettingsService

        db = get_sessionmaker()()
        try:
            cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
            validated = validate_meta_whatsapp_config(cfg or {})
            token = str(validated.get("access_token") or "").strip()
            phone_number_id = str(validated.get("phone_number_id") or "").strip()
            phone = str(validated.get("whatsapp_from") or os.environ.get("META_PHONE_NUMBER") or DEFAULT_PHONE).strip()
            if token and phone_number_id:
                return {
                    "phone": phone or DEFAULT_PHONE,
                    "access_token": token,
                    "phone_number_id": phone_number_id,
                    "pin": str(os.environ.get("META_WHATSAPP_PIN") or "").strip(),
                    "graph_version": str(
                        validated.get("graph_api_version") or os.environ.get("META_GRAPH_API_VERSION") or DEFAULT_GRAPH_VERSION
                    ).strip(),
                }
        finally:
            db.close()
    except Exception as exc:
        print(f"DB config fallback unavailable: {exc}", file=sys.stderr)
    return None


def _meta_config(*, use_db: bool = False) -> dict[str, str]:
    _load_dotenv()
    phone = str(os.environ.get("META_PHONE_NUMBER") or DEFAULT_PHONE).strip() or DEFAULT_PHONE
    access_token = str(os.environ.get("META_ACCESS_TOKEN") or "").strip()
    phone_number_id = str(os.environ.get("META_PHONE_NUMBER_ID") or "").strip()
    pin = str(os.environ.get("META_WHATSAPP_PIN") or "").strip()
    graph_version = str(os.environ.get("META_GRAPH_API_VERSION") or DEFAULT_GRAPH_VERSION).strip()
    if graph_version and not graph_version.startswith("v"):
        graph_version = f"v{graph_version}"

    if (not access_token or not phone_number_id) and use_db:
        db_cfg = _config_from_db()
        if db_cfg:
            print("Using Meta credentials from Admin → Integrations (DB).")
            if not pin and db_cfg.get("pin"):
                pin = db_cfg["pin"]
            access_token = access_token or db_cfg["access_token"]
            phone_number_id = phone_number_id or db_cfg["phone_number_id"]
            phone = phone or db_cfg["phone"]
            graph_version = graph_version or db_cfg["graph_version"]

    missing = [name for name, val in (
        ("META_ACCESS_TOKEN", access_token),
        ("META_PHONE_NUMBER_ID", phone_number_id),
    ) if not val]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print("Set them in voxbulk-api/.env or pass --from-db (Admin integration).", file=sys.stderr)
        sys.exit(1)
    return {
        "phone": phone,
        "access_token": access_token,
        "phone_number_id": phone_number_id,
        "pin": pin,
        "graph_version": graph_version or DEFAULT_GRAPH_VERSION,
    }


def _graph_url(cfg: dict[str, str], path: str) -> str:
    version = cfg["graph_version"]
    phone_number_id = cfg["phone_number_id"]
    base = f"https://graph.facebook.com/{version}"
    if path == "register":
        return f"{base}/{phone_number_id}/register"
    if path == "request_code":
        return f"{base}/{phone_number_id}/request_code"
    if path == "verify_code":
        return f"{base}/{phone_number_id}/verify_code"
    raise ValueError(f"Unknown path: {path}")


def _post(cfg: dict[str, str], *, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
    url = _graph_url(cfg, path)
    headers = {"Authorization": f"Bearer {cfg['access_token']}"}
    print(f"POST {url}")
    print(f"Phone number (E.164): {cfg['phone']}")
    print(f"Request body: {json.dumps({k: ('***' if k == 'pin' else v) for k, v in body.items()})}")
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        print(f"HTTP client error: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        payload: dict[str, Any] | str = response.json()
    except ValueError:
        payload = response.text
    print(f"HTTP status: {response.status_code}")
    if isinstance(payload, dict):
        print(json.dumps(payload, indent=2))
    else:
        print(payload)
    return response.status_code, payload


def _pin_or_verify_error(status: int, payload: dict[str, Any] | str) -> bool:
    if status < 400:
        return False
    text = json.dumps(payload).lower() if isinstance(payload, dict) else str(payload).lower()
    return any(marker in text for marker in _PIN_ERROR_MARKERS)


def cmd_register(cfg: dict[str, str]) -> int:
    if not cfg["pin"]:
        print("META_WHATSAPP_PIN is not set in .env — required for register.", file=sys.stderr)
        print("If Meta needs SMS verification first, run:", file=sys.stderr)
        print("  python scripts/register_whatsapp_number.py --request-code", file=sys.stderr)
        return 1
    status, payload = _post(
        cfg,
        path="register",
        body={"messaging_product": "whatsapp", "pin": cfg["pin"]},
    )
    if status >= 400 and _pin_or_verify_error(status, payload):
        print(
            "\nRegistration failed — PIN may be wrong or Meta requires SMS verification.\n"
            "Run: python scripts/register_whatsapp_number.py --request-code\n"
            "Then: python scripts/register_whatsapp_number.py --verify-code <code>"
        )
        return 1
    return 0 if status < 400 else 1


def cmd_request_code(cfg: dict[str, str]) -> int:
    status, payload = _post(
        cfg,
        path="request_code",
        body={"code_method": "SMS", "language": "en"},
    )
    if status < 400:
        print(f"\nVerification code requested via SMS for {cfg['phone']}.")
    return 0 if status < 400 else 1


def cmd_verify_code(cfg: dict[str, str], code: str) -> int:
    code = str(code or "").strip()
    if not code:
        print("--verify-code requires a numeric code", file=sys.stderr)
        return 1
    status, payload = _post(cfg, path="verify_code", body={"code": code})
    if status < 400:
        print(f"\nCode accepted for {cfg['phone']}. Re-run without flags to register with PIN:")
        print("  python scripts/register_whatsapp_number.py")
    return 0 if status < 400 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register Meta WhatsApp Cloud API phone number (+447822002099 default)"
    )
    parser.add_argument(
        "--request-code",
        action="store_true",
        help="Request SMS verification code from Meta",
    )
    parser.add_argument(
        "--verify-code",
        metavar="CODE",
        help="Verify SMS code from Meta",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Load META_ACCESS_TOKEN and META_PHONE_NUMBER_ID from Admin integration when not in .env",
    )
    args = parser.parse_args()
    cfg = _meta_config(use_db=args.from_db)

    if args.verify_code is not None:
        return cmd_verify_code(cfg, args.verify_code)
    if args.request_code:
        return cmd_request_code(cfg)
    return cmd_register(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
