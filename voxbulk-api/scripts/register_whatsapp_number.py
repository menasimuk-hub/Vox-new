#!/usr/bin/env python3
"""Register a Meta WhatsApp Cloud API number (e.g. +447822002099 / Connection Profile Meta 99).

Copy-paste on VPS:
  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate

  # Best: load token + phone_number_id from Connection Profile "Meta 99"
  python scripts/register_whatsapp_number.py --profile "Meta 99" --interactive

  # Or step by step:
  python scripts/register_whatsapp_number.py --profile "Meta 99" --request-code
  python scripts/register_whatsapp_number.py --profile "Meta 99" --verify-code 123456
  # Add META_WHATSAPP_PIN=sixdigits to .env first, then:
  python scripts/register_whatsapp_number.py --profile "Meta 99"

SMS code arrives on the handset/SIM for the number (not in VoxBulk Admin).
Two-step PIN is set in Meta WhatsApp Manager for that number.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.meta_whatsapp_register_service import (
    DEFAULT_GRAPH_VERSION,
    register_phone_number,
    request_verification_code,
    verify_verification_code,
)

DEFAULT_PHONE = "+447822002099"


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


def _config_from_integration() -> dict[str, str] | None:
    from app.core.database import get_sessionmaker
    from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
    from app.services.provider_settings import ProviderSettingsService

    db = get_sessionmaker()()
    try:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        validated = validate_meta_whatsapp_config(cfg or {})
        token = str(validated.get("access_token") or "").strip()
        phone_number_id = str(validated.get("phone_number_id") or "").strip()
        phone = str(validated.get("whatsapp_from") or "").strip()
        if token and phone_number_id:
            return {
                "phone": phone or DEFAULT_PHONE,
                "access_token": token,
                "phone_number_id": phone_number_id,
                "graph_version": str(validated.get("graph_api_version") or DEFAULT_GRAPH_VERSION),
                "source": "Admin → Integrations → Meta WhatsApp",
            }
    finally:
        db.close()
    return None


def _config_from_connection_profile(profile_name: str) -> dict[str, str] | None:
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.connection_profile import CHANNEL_WHATSAPP, PROVIDER_META, ConnectionProfile
    from app.services.connection.profile_credentials import meta_config_from_profile

    db = get_sessionmaker()()
    try:
        row = db.execute(
            select(ConnectionProfile)
            .where(ConnectionProfile.channel == CHANNEL_WHATSAPP)
            .where(ConnectionProfile.provider == PROVIDER_META)
            .where(ConnectionProfile.name == profile_name)
        ).scalar_one_or_none()
        if row is None:
            rows = db.execute(
                select(ConnectionProfile)
                .where(ConnectionProfile.channel == CHANNEL_WHATSAPP)
                .where(ConnectionProfile.provider == PROVIDER_META)
            ).scalars().all()
            names = [r.name for r in rows]
            print(f'Connection profile "{profile_name}" not found. Meta profiles: {names or "(none)"}', file=sys.stderr)
            return None
        meta = meta_config_from_profile(row)
        token = str(meta.get("access_token") or "").strip()
        phone_number_id = str(meta.get("phone_number_id") or row.meta_phone_number_id or "").strip()
        phone = str(meta.get("whatsapp_from") or row.meta_whatsapp_from or row.telnyx_number or DEFAULT_PHONE).strip()
        if not token or not phone_number_id:
            print(
                f'Profile "{profile_name}" is missing meta_access_token or meta_phone_number_id — save it in Admin first.',
                file=sys.stderr,
            )
            return None
        return {
            "phone": phone or DEFAULT_PHONE,
            "access_token": token,
            "phone_number_id": phone_number_id,
            "graph_version": DEFAULT_GRAPH_VERSION,
            "source": f'Connection Profile "{row.name}" ({row.id})',
        }
    finally:
        db.close()


def _meta_config(*, profile: str | None, use_db: bool) -> dict[str, str]:
    _load_dotenv()
    phone = str(os.environ.get("META_PHONE_NUMBER") or DEFAULT_PHONE).strip() or DEFAULT_PHONE
    access_token = str(os.environ.get("META_ACCESS_TOKEN") or "").strip()
    phone_number_id = str(os.environ.get("META_PHONE_NUMBER_ID") or "").strip()
    pin = str(os.environ.get("META_WHATSAPP_PIN") or "").strip()
    graph_version = str(os.environ.get("META_GRAPH_API_VERSION") or DEFAULT_GRAPH_VERSION).strip()
    source = ".env"

    if profile:
        prof = _config_from_connection_profile(profile)
        if prof is None:
            sys.exit(1)
        print(f"Using {prof['source']}")
        access_token = access_token or prof["access_token"]
        phone_number_id = phone_number_id or prof["phone_number_id"]
        phone = prof["phone"] or phone
        graph_version = prof.get("graph_version") or graph_version
        source = prof["source"]
    elif (not access_token or not phone_number_id) and use_db:
        integ = _config_from_integration()
        if integ:
            print(f"Using {integ['source']}")
            access_token = access_token or integ["access_token"]
            phone_number_id = phone_number_id or integ["phone_number_id"]
            phone = integ["phone"] or phone
            graph_version = integ.get("graph_version") or graph_version
            source = integ["source"]

    if graph_version and not graph_version.startswith("v"):
        graph_version = f"v{graph_version}"

    missing = [n for n, v in (("META_ACCESS_TOKEN", access_token), ("META_PHONE_NUMBER_ID", phone_number_id)) if not v]
    if missing:
        print(f"Missing: {', '.join(missing)}", file=sys.stderr)
        print('Use --profile "Meta 99" or set META_* in .env', file=sys.stderr)
        sys.exit(1)

    return {
        "phone": phone,
        "access_token": access_token,
        "phone_number_id": phone_number_id,
        "pin": pin,
        "graph_version": graph_version,
        "source": source,
    }


def _print_result(result: dict[str, Any]) -> int:
    print(f"Phone: {result.get('phone')}")
    print(f"POST {result.get('url')}")
    print(f"HTTP {result.get('status_code')}")
    payload = result.get("payload")
    if isinstance(payload, dict):
        print(json.dumps(payload, indent=2))
    elif payload:
        print(payload)
    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
    return 0 if result.get("ok") else 1


def cmd_request_code(cfg: dict[str, str]) -> int:
    result = request_verification_code(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
    )
    rc = _print_result(result)
    if result.get("ok"):
        print(f"\nSMS sent to {cfg['phone']} — check the phone/SIM (not VoxBulk Admin).")
        print("Then: python scripts/register_whatsapp_number.py --profile \"Meta 99\" --verify-code YOUR_CODE")
    return rc


def cmd_verify_code(cfg: dict[str, str], code: str) -> int:
    result = verify_verification_code(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        code=code,
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
    )
    rc = _print_result(result)
    if result.get("ok"):
        print(f"\nCode OK. Now register with two-step PIN:")
        print('  python scripts/register_whatsapp_number.py --profile "Meta 99"')
    return rc


def cmd_register(cfg: dict[str, str]) -> int:
    pin = cfg.get("pin") or ""
    if not pin:
        pin = getpass.getpass("Meta two-step PIN (6 digits, from WhatsApp Manager): ").strip()
    if not pin:
        print("Set META_WHATSAPP_PIN in .env or enter PIN when prompted.", file=sys.stderr)
        return 1
    result = register_phone_number(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        pin=pin,
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
    )
    rc = _print_result(result)
    if result.get("ok"):
        print(f"\nRegistered {cfg['phone']} with Meta Cloud API.")
        print("Check: https://business.facebook.com/latest/whatsapp_manager/phone_numbers")
    elif result.get("needs_sms_verify"):
        print("\nTry SMS verification first: --request-code then --verify-code", file=sys.stderr)
    return rc


def cmd_interactive(cfg: dict[str, str]) -> int:
    print(f"=== Step 1/3: Request SMS code for {cfg['phone']} ===")
    if cmd_request_code(cfg) != 0:
        return 1
    code = input("\nEnter the SMS code received on the phone (6 digits): ").strip()
    print(f"\n=== Step 2/3: Verify code ===")
    if cmd_verify_code(cfg, code) != 0:
        return 1
    print(f"\n=== Step 3/3: Register with two-step PIN ===")
    return cmd_register(cfg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta WhatsApp phone register (+447822002099)")
    parser.add_argument("--profile", metavar="NAME", help='Connection profile name, e.g. "Meta 99"')
    parser.add_argument("--from-db", action="store_true", help="Fallback: Admin Integrations Meta config")
    parser.add_argument("--request-code", action="store_true", help="Send SMS verification code")
    parser.add_argument("--verify-code", metavar="CODE", help="Verify SMS code")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Request SMS → prompt for code → register (all in one run)",
    )
    args = parser.parse_args()
    cfg = _meta_config(profile=args.profile, use_db=args.from_db)

    if args.interactive:
        return cmd_interactive(cfg)
    if args.verify_code is not None:
        return cmd_verify_code(cfg, args.verify_code)
    if args.request_code:
        return cmd_request_code(cfg)
    return cmd_register(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
