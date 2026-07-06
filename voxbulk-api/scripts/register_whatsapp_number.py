#!/usr/bin/env python3
"""Register a Meta WhatsApp Cloud API number (e.g. +447822002099 / Connection Profile Meta 99).

Full flow (copy-paste on VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  git pull origin main
  python scripts/register_whatsapp_number.py --profile "Meta 99" --full-register

This will: request SMS code → you paste code when received → you choose a PIN → register.
The PIN is NOT sent by Meta — you pick any 6 digits (two-step verification for this number).
Do NOT put a demo PIN in .env unless you chose that PIN yourself in WhatsApp Manager.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.meta_whatsapp_register_service import (
    DEFAULT_GRAPH_VERSION,
    get_phone_number_status,
    register_phone_number,
    request_verification_code,
    verify_verification_code,
)

_CODE_RE = re.compile(r"\b(\d{6})\b")

DEFAULT_PHONE = "+447822002099"
CODE_LOG_FILE = ROOT / "meta_last_verify_code.txt"
REGISTER_LOG_FILE = ROOT / "meta_register_result.txt"


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


def _extract_code_from_text(text: str) -> str | None:
    match = _CODE_RE.search(str(text or ""))
    return match.group(1) if match else None


def _phone_status_payload(cfg: dict[str, str]) -> dict[str, Any]:
    result = get_phone_number_status(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        graph_version=cfg["graph_version"],
    )
    payload = result.get("payload")
    return payload if isinstance(payload, dict) else {}


def _is_phone_verified(payload: dict[str, Any]) -> bool:
    return str(payload.get("code_verification_status") or "").upper() == "VERIFIED"


def _meta_error_already_verified(result: dict[str, Any]) -> bool:
    payload = result.get("payload")
    if not isinstance(payload, dict):
        return False
    err = payload.get("error")
    if not isinstance(err, dict):
        return False
    if err.get("code") == 136024:
        return True
    msg = str(err.get("error_user_msg") or err.get("message") or "").lower()
    return "already verified" in msg


def _scan_log_rows(rows: list[dict], *, phone_e164: str, seen_ids: set[int]) -> str | None:
    digits = re.sub(r"\D", "", phone_e164)
    tail = digits[-10:] if len(digits) >= 10 else digits
    for row in rows:
        row_id = int(row.get("id") or 0)
        if row_id in seen_ids:
            continue
        direction = str(row.get("direction") or "").lower()
        if direction not in {"inbound", "in", "incoming", ""}:
            seen_ids.add(row_id)
            continue
        to_num = re.sub(r"\D", "", str(row.get("to_number") or ""))
        from_num = re.sub(r"\D", "", str(row.get("from_number") or ""))
        body = str(row.get("body") or "")
        haystack = f"{to_num} {from_num} {body}".lower()
        if tail and tail not in haystack and "verif" not in haystack:
            seen_ids.add(row_id)
            continue
        code = _extract_code_from_text(body)
        if code:
            provider = row.get("provider") or "unknown"
            print(
                f"Found code in {provider} message log id={row_id} "
                f"from={row.get('from_number')} body={body[:200]!r}"
            )
            return code
        seen_ids.add(row_id)
    return None


def _poll_webhook_events(phone_e164: str, *, seen_ids: set[int]) -> str | None:
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.webhook_event import WebhookEvent

    digits = re.sub(r"\D", "", phone_e164)
    tail = digits[-10:] if len(digits) >= 10 else digits
    db = get_sessionmaker()()
    try:
        rows = db.execute(
            select(WebhookEvent)
            .where(WebhookEvent.provider.in_(("meta_whatsapp", "telnyx")))
            .order_by(WebhookEvent.id.desc())
            .limit(120)
        ).scalars().all()
    finally:
        db.close()
    for row in rows:
        row_id = int(row.id or 0)
        if row_id in seen_ids:
            continue
        raw = str(row.raw_body or "")
        haystack = raw.lower()
        if tail and tail not in re.sub(r"\D", "", raw) and "verif" not in haystack:
            seen_ids.add(row_id)
            continue
        code = _extract_code_from_text(raw)
        if code:
            print(f"Found code in webhook_events id={row_id} provider={row.provider}")
            return code
        seen_ids.add(row_id)
    return None


def _poll_inbound_verification_code(phone_e164: str, *, wait_seconds: int = 180) -> str | None:
    """Read Meta verify code from message webhooks (Meta WA + Telnyx SMS), not a handset."""
    from app.core.database import get_sessionmaker
    from app.services.messaging_log_service import LogService

    deadline = time.time() + max(30, wait_seconds)
    seen_log_ids: set[int] = set()
    seen_event_ids: set[int] = set()
    print(f"Polling message webhooks for {phone_e164} (up to {wait_seconds}s)...")
    print("Sources: /webhooks/meta/whatsapp + /telnyx/webhooks/messages → whatsapp_logs + webhook_events")
    while time.time() < deadline:
        db = get_sessionmaker()()
        try:
            for provider in ("meta_whatsapp", "telnyx"):
                rows = LogService.list_platform_message_logs(
                    db,
                    limit=80,
                    to_number=phone_e164,
                    provider=provider,
                )
                if not rows:
                    rows = LogService.list_platform_message_logs(db, limit=120, provider=provider, q="verif")
                code = _scan_log_rows(rows, phone_e164=phone_e164, seen_ids=seen_log_ids)
                if code:
                    return code
        finally:
            db.close()
        code = _poll_webhook_events(phone_e164, seen_ids=seen_event_ids)
        if code:
            return code
        time.sleep(5)
    return None


def cmd_status(cfg: dict[str, str]) -> int:
    result = get_phone_number_status(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        graph_version=cfg["graph_version"],
    )
    print(json.dumps(result.get("payload") or result, indent=2))
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    cv = str(payload.get("code_verification_status") or "")
    if cv:
        print(f"\ncode_verification_status={cv}")
        if cv.upper() == "VERIFIED":
            print('Number already verified — run: python scripts/register_whatsapp_number.py --profile "Meta 99" --register-only')
    return 0 if result.get("ok") else 1


def cmd_request_code(cfg: dict[str, str], *, code_method: str = "SMS") -> int:
    result = request_verification_code(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
        code_method=code_method,
    )
    if not result.get("ok") and _meta_error_already_verified(result):
        print("Meta: phone number already verified — skip verify step, go to PIN register.")
        return 0
    rc = _print_result(result)
    if result.get("ok"):
        via = "voice call" if code_method.upper() == "VOICE" else "SMS"
        print(f"\nMeta sent a {via} to {cfg['phone']}.")
        print("API-only: script polls message webhooks for the code (no handset needed).")
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


def _save_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    print(f"Saved → {path}")


def cmd_register(cfg: dict[str, str], *, pin: str | None = None) -> int:
    chosen = str(pin or cfg.get("pin") or "").strip()
    if not chosen:
        print(
            "\nTwo-step PIN: Meta does NOT send this. YOU choose any 6 digits.\n"
            "If the number has no PIN yet, pick a new one (remember it for WhatsApp Manager).\n"
            "If you already set a PIN in Meta, enter that same PIN.\n"
        )
        chosen = getpass.getpass("Enter 6-digit two-step PIN: ").strip()
    if not chosen or len(chosen) != 6 or not chosen.isdigit():
        print("PIN must be exactly 6 digits.", file=sys.stderr)
        return 1
    result = register_phone_number(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        pin=chosen,
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
    )
    rc = _print_result(result)
    if result.get("ok"):
        msg = f"registered phone={cfg['phone']} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        _save_text(REGISTER_LOG_FILE, msg)
        print(f"\nRegistered {cfg['phone']} with Meta Cloud API.")
        print("Check: https://business.facebook.com/latest/whatsapp_manager/phone_numbers")
    elif result.get("needs_sms_verify"):
        print("\nTry SMS verification first: --request-code then --verify-code", file=sys.stderr)
    return rc


def cmd_full_register(cfg: dict[str, str], *, code_method: str = "SMS", wait_seconds: int = 180) -> int:
    """API-only: request code → poll webhooks → verify (if needed) → register."""
    print(f"=== Meta 99 full register for {cfg['phone']} ===")
    print(f"Config from: {cfg.get('source', 'unknown')}\n")

    payload = _phone_status_payload(cfg)
    print(json.dumps(payload, indent=2))
    cv = str(payload.get("code_verification_status") or "")
    if cv:
        print(f"\ncode_verification_status={cv}")

    if _is_phone_verified(payload):
        print("\nAlready verified on Meta — skipping SMS code. Enter your two-step PIN to register.")
        return cmd_register(cfg)

    print(f"\n=== Step 1: Request verification code ({code_method}) ===")
    req = request_verification_code(
        access_token=cfg["access_token"],
        phone_number_id=cfg["phone_number_id"],
        phone_e164=cfg["phone"],
        graph_version=cfg["graph_version"],
        code_method=code_method,
    )
    if not req.get("ok"):
        if _meta_error_already_verified(req):
            print("Meta: already verified — skipping to PIN register.")
            return cmd_register(cfg)
        return _print_result(req)

    _print_result(req)
    via = "voice call" if code_method.upper() == "VOICE" else "SMS"
    print(f"\nMeta sent a {via}. Polling message webhooks for up to {wait_seconds}s...")

    code = _poll_inbound_verification_code(cfg["phone"], wait_seconds=wait_seconds)
    if not code:
        print("\nNo code in webhooks yet. Paste it if you have it (or Ctrl+C and retry).")
        for _attempt in range(3):
            code = input("Paste the 6-digit verification code here: ").strip()
            if code and len(code) == 6 and code.isdigit():
                break
            print("Need exactly 6 digits.", file=sys.stderr)
            code = ""
    if not code:
        return 1

    _save_text(CODE_LOG_FILE, code)
    print(f"Verification code recorded: {code}")

    print(f"\n=== Step 2: Verify code with Meta ===")
    if cmd_verify_code(cfg, code) != 0:
        return 1

    print(f"\n=== Step 3: Register (two-step PIN — you choose, not Meta) ===")
    return cmd_register(cfg)


def cmd_interactive(cfg: dict[str, str], *, code_method: str = "SMS", wait_seconds: int = 0) -> int:
    cmd_status(cfg)
    if cmd_request_code(cfg, code_method=code_method) != 0:
        return 1
    code = ""
    if wait_seconds > 0:
        found = _poll_inbound_verification_code(cfg["phone"], wait_seconds=wait_seconds)
        if found:
            code = found
            _save_text(CODE_LOG_FILE, code)
    if not code:
        code = input("\nPaste 6-digit verification code: ").strip()
    if cmd_verify_code(cfg, code) != 0:
        return 1
    return cmd_register(cfg)


def cmd_wait_inbound(cfg: dict[str, str], wait_seconds: int) -> int:
    code = _poll_inbound_verification_code(cfg["phone"], wait_seconds=wait_seconds)
    if not code:
        print("\nNo code in message webhooks yet. Paste manually or retry with --full-register.", file=sys.stderr)
        return 1
    _save_text(CODE_LOG_FILE, code)
    print(f"\nUse: python scripts/register_whatsapp_number.py --profile \"Meta 99\" --verify-code {code}")
    return cmd_verify_code(cfg, code)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta WhatsApp phone register (+447822002099)")
    parser.add_argument("--profile", metavar="NAME", help='Connection profile name, e.g. "Meta 99"')
    parser.add_argument("--from-db", action="store_true", help="Fallback: Admin Integrations Meta config")
    parser.add_argument("--request-code", action="store_true", help="Send SMS/voice verification code")
    parser.add_argument(
        "--method",
        choices=("sms", "voice", "SMS", "VOICE"),
        default="sms",
        help="Delivery for --request-code: sms or voice (try voice if no SMS on Telnyx)",
    )
    parser.add_argument("--verify-code", metavar="CODE", help="Verify SMS/voice code")
    parser.add_argument("--status", action="store_true", help="Show Meta phone status from Graph API")
    parser.add_argument(
        "--register-only",
        action="store_true",
        help="Skip verify — number already verified; prompt for PIN and register",
    )
    parser.add_argument(
        "--wait-inbound",
        nargs="?",
        const=180,
        type=int,
        metavar="SECONDS",
        help="Alias for --wait-webhook (poll message webhooks)",
    )
    parser.add_argument(
        "--full-register",
        action="store_true",
        help="Request code → paste code → verify → register (recommended for Meta 99)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Same as --full-register",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Request + poll message webhooks + verify + register (API-only numbers)",
    )
    args = parser.parse_args()
    cfg = _meta_config(profile=args.profile, use_db=args.from_db)
    method = str(args.method or "sms").upper()
    wait = int(args.wait_inbound or 180) if args.wait_inbound is not None else 180

    if args.status:
        return cmd_status(cfg)
    if args.register_only:
        return cmd_register(cfg)
    if args.full_register or args.interactive:
        return cmd_full_register(cfg, code_method=method, wait_seconds=wait)
    if args.api_only:
        return cmd_interactive(cfg, code_method=method, wait_seconds=180)
    if args.verify_code is not None:
        return cmd_verify_code(cfg, args.verify_code)
    if args.request_code:
        rc = cmd_request_code(cfg, code_method=method)
        if rc == 0 and args.wait_inbound is not None:
            return cmd_wait_inbound(cfg, int(args.wait_inbound or 180))
        return rc
    if args.wait_inbound is not None:
        return cmd_wait_inbound(cfg, int(args.wait_inbound or 180))
    return cmd_register(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
