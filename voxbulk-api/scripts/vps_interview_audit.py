#!/usr/bin/env python3
"""
VPS interview workflow + config audit. Run on the server after deploy:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/vps_interview_audit.py
  python3 scripts/vps_interview_audit.py --check-api   # also probe local :8000 routes

Exits 0 when all checks pass, 1 when any FAIL (fix before relying on launch/email).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent


def _ok(msg: str) -> None:
    print(f"  OK   {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def _warn(msg: str) -> None:
    print(f"  WARN {msg}")


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _load_settings():
    sys.path.insert(0, str(API_ROOT))
    os.chdir(API_ROOT)
    from app.core.config import get_settings

    return get_settings()


def check_git_deploy() -> list[str]:
    errors: list[str] = []
    _section("Git / deploy")
    try:
        head = (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True)
            .strip()
        )
        _ok(f"HEAD {head}")
        log = subprocess.check_output(
            ["git", "log", "-1", "--oneline"],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
        _ok(log)
        if "ensure_full_day_booking_window" not in Path(
            REPO_ROOT / "voxbulk-api/app/services/interview_launch_service.py"
        ).read_text(encoding="utf-8"):
            _fail("interview_launch_service.py missing ensure_full_day_booking_window import (launch 500)")
            errors.append("launch_import")
        else:
            _ok("launch imports ensure_full_day_booking_window (not the broken class method)")
    except Exception as exc:
        _warn(f"git check skipped: {exc}")
    return errors


def check_env() -> list[str]:
    errors: list[str] = []
    _section("Environment (.env)")
    settings = _load_settings()
    slot = int(getattr(settings, "interview_slot_minutes", 0) or 0)
    relax = bool(getattr(settings, "interview_relax_hours", False))
    booking_origin = str(getattr(settings, "booking_app_origin", "") or "").strip()
    dash_origin = str(getattr(settings, "dashboard_app_origin", "") or "").strip()
    telnyx = str(getattr(settings, "interview_telnyx_assistant_id", "") or "").strip()
    api_key = str(getattr(settings, "telnyx_api_key", "") or "").strip()

    if 1 <= slot <= 60:
        _ok(f"INTERVIEW_SLOT_MINUTES={slot}")
    else:
        _fail(f"INTERVIEW_SLOT_MINUTES invalid: {slot}")
        errors.append("slot_minutes")

    if relax:
        _ok("INTERVIEW_RELAX_HOURS=1 (24h booking + dial relax)")
    else:
        _warn("INTERVIEW_RELAX_HOURS off — 9:00–17:30 UK calling cap applies")

    if booking_origin:
        _ok(f"BOOKING_APP_ORIGIN={booking_origin}")
    elif dash_origin and "dashboard" in dash_origin:
        _ok(f"booking links use DASHBOARD_APP_ORIGIN={dash_origin}")
    else:
        _warn("BOOKING_APP_ORIGIN empty — booking emails may use localhost links")

    if telnyx or api_key:
        _ok("Telnyx configured (key and/or INTERVIEW_TELNYX_ASSISTANT_ID)")
    else:
        _warn("Telnyx interview assistant not set in env — calls may fail")

    trusted = str(os.environ.get("TRUSTED_HOSTS", "") or getattr(settings, "trusted_hosts", "") or "")
    if "api.voxbulk.com" in trusted or not trusted:
        _ok("TRUSTED_HOSTS looks fine for api.voxbulk.com")
    else:
        _warn(f"TRUSTED_HOSTS may block API: {trusted[:80]}")

    return errors


def check_smtp_and_email(db) -> list[str]:
    errors: list[str] = []
    _section("SMTP + interview email")
    from app.services.career_email_service import interview_email_delivery_status, smtp_from_address
    from app.services.smtp_settings_service import SmtpSettingsService

    row = SmtpSettingsService.get_row(db)
    configured, missing = SmtpSettingsService.compute_status(row)
    delivery = interview_email_delivery_status(db)
    from_name, from_email = smtp_from_address(db)

    if configured:
        _ok("SMTP row complete")
    else:
        _fail(f"SMTP incomplete: {', '.join(missing)}")
        errors.append("smtp_incomplete")

    if row.is_enabled:
        _ok("SMTP enabled")
    else:
        _fail("SMTP disabled in Admin → Email")
        errors.append("smtp_disabled")

    _ok(f"Interview From (SMTP): {from_name} <{from_email}>")
    _ok(f"Reply-To (careers): {delivery.get('careers_reply_to')}")

    if from_email and "@" in from_email:
        if from_email.lower() == "careers@voxbulk.com" and (row.from_email or "").lower() != from_email.lower():
            _warn(
                "SMTP from_email in DB differs from careers@ — interview now uses DB from_email (good); "
                "ensure SMTP allows that address"
            )
    else:
        _fail("No valid SMTP from_email for interview sends")
        errors.append("smtp_from")

    if delivery.get("can_send_email"):
        _ok("can_send_email=true")
    else:
        _fail("can_send_email=false — invites will not send")
        errors.append("cannot_send")

    return errors


def check_templates(db) -> list[str]:
    errors: list[str] = []
    _section("Email templates")
    from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService

    EmailTemplateService.ensure_system_templates(db)
    required = [
        "interview_booking_invite",
        "interview_booking_confirm",
        "interview_booking_cancel",
        "interview_campaign_cancelled",
    ]
    for key in required:
        subject, body, enabled = EmailTemplateService.get_send_content(db, key=key)
        if subject.strip() or body.strip():
            _ok(f"{key} has content (enabled={enabled})")
        else:
            _fail(f"{key} empty in DB and defaults")
            errors.append(f"tpl_{key}")
    unknown = [k for k in required if k not in EMAIL_TEMPLATE_KEYS]
    if unknown:
        _fail(f"template keys missing from registry: {unknown}")
    return errors


def check_code_imports() -> list[str]:
    errors: list[str] = []
    _section("Critical imports (launch / email)")
    try:
        mod = importlib.import_module("app.services.interview_launch_service")
        if not hasattr(mod, "ensure_full_day_booking_window"):
            from app.services.interview_booking_service import ensure_full_day_booking_window  # noqa: F401

            _ok("ensure_full_day_booking_window importable")
        importlib.import_module("app.services.career_email_service")
        _ok("career_email_service loads")
    except Exception as exc:
        _fail(f"import error: {exc}")
        errors.append("import")
    return errors


def check_local_api(base: str) -> list[str]:
    errors: list[str] = []
    _section(f"HTTP probe {base}")

    def get(path: str) -> tuple[int, str]:
        try:
            req = Request(f"{base.rstrip('/')}{path}", headers={"Accept": "application/json"})
            with urlopen(req, timeout=8) as resp:
                return resp.status, resp.read(500).decode("utf-8", errors="replace")
        except URLError as exc:
            return 0, str(exc)

    code, body = get("/health")
    if code == 200 and "ok" in body:
        _ok("/health")
    else:
        _fail(f"/health → {code} {body[:120]}")
        errors.append("health")

    for path in ("/public/brand",):
        code, _ = get(path)
        if code == 200:
            _ok(path)
        else:
            _warn(f"{path} → HTTP {code}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="VoxBulk VPS interview audit")
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Probe http://127.0.0.1:8000 (API must be running)",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("VOXBULK_AUDIT_API_BASE", "http://127.0.0.1:8000"),
    )
    args = parser.parse_args()

    print("VoxBulk interview VPS audit")
    print(f"API root: {API_ROOT}")

    all_errors: list[str] = []
    all_errors.extend(check_git_deploy())
    all_errors.extend(check_code_imports())
    all_errors.extend(check_env())

    sys.path.insert(0, str(API_ROOT))
    os.chdir(API_ROOT)
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        all_errors.extend(check_smtp_and_email(db))
        all_errors.extend(check_templates(db))

    if args.check_api:
        all_errors.extend(check_local_api(args.api_base))

    _section("Summary")
    if all_errors:
        print(f"FAILED ({len(all_errors)} issue(s)): {', '.join(sorted(set(all_errors)))}")
        print("\nNext steps:")
        print("  1. git pull origin main && ./deploy-vps.sh")
        print("  2. Admin → Email: enable SMTP, send-test, note from_email")
        print("  3. voxbulk-api/.env: INTERVIEW_SLOT_MINUTES=4, INTERVIEW_RELAX_HOURS=1, BOOKING_APP_ORIGIN=https://dashboard.voxbulk.com")
        print("  4. ./vox.sh restart")
        print("  5. bash scripts/e2e_interview_workflow_test.sh  (set VOXBULK_EMAIL/PASSWORD)")
        return 1

    print("All checks passed.")
    print("Run one real invite email (same code as launch):")
    print("  python3 scripts/send_interview_invite_email_test.py --to you@company.com")
    print("Run E2E: export VOXBULK_API_BASE_URL=https://api.voxbulk.com VOXBULK_EMAIL=... VOXBULK_PASSWORD=...")
    print("         bash scripts/e2e_interview_workflow_test.sh --send-test-emails")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
