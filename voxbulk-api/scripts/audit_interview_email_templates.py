#!/usr/bin/env python3
"""
Verify interview email flows point at the correct repo template keys.
Run from voxbulk-api: python scripts/audit_interview_email_templates.py
"""

from __future__ import annotations

import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)

# Expected: user-facing flow -> template_key in code -> defaults in repo
EXPECTED_FLOWS: list[tuple[str, str, str]] = [
    ("Launch / resend invites", "interview_booking_service.send_invites", "interview_booking_invite"),
    ("Book slot (confirm)", "career_email_service.send_booking_confirm_email", "interview_booking_confirm"),
    ("Reschedule (rebook)", "interview_booking_service._send_booking_confirmations", "interview_booking_confirm"),
    ("30 min reminder", "career_email_service.send_booking_reminder_email", "interview_booking_reminder"),
    ("Candidate cancel slot", "interview_booking_service._send_booking_cancellation", "interview_booking_cancel"),
    ("Employer stop (no slot)", "notify_campaign_closed", "interview_campaign_cancelled"),
    ("Employer stop (had slot)", "notify_campaign_closed + _send_booking_cancellation", "interview_booking_cancel"),
]

INTERVIEW_KEYS = (
    "interview_scheduling_invite",
    "interview_booking_invite",
    "interview_booking_confirm",
    "interview_booking_reminder",
    "interview_booking_cancel",
    "interview_campaign_cancelled",
    "interview_meeting_missed",
)


def _read(path: str) -> str:
    with open(os.path.join(API_ROOT, path), encoding="utf-8") as f:
        return f.read()


def _code_checks() -> list[str]:
    errors: list[str] = []
    booking = _read("app/services/interview_booking_service.py")
    career = _read("app/services/career_email_service.py")
    reminder = _read("app/services/interview_booking_reminder_service.py")

    pairs = [
        ("invite", "template_key=\"interview_booking_invite\"", booking),
        ("confirm (career)", "template_key=\"interview_booking_confirm\"", career),
        ("cancel slot", "template_key=\"interview_booking_cancel\"", booking),
        ("campaign stop", "template_key=\"interview_campaign_cancelled\"", booking),
        ("reminder", "template_key=\"interview_booking_reminder\"", career),
    ]
    for name, needle, text in pairs:
        if needle not in text:
            errors.append(f"code_missing:{name}:{needle}")

    if "send_booking_confirm_email" not in booking:
        errors.append("reschedule_must_call_send_booking_confirmations")
    if booking.count("def reschedule_booking") != 1:
        errors.append("reschedule_booking_missing")
    if "_send_booking_confirmations" not in booking[booking.find("def reschedule_booking") :]:
        errors.append("reschedule_does_not_call_send_booking_confirmations")

    if "send_invites" in booking and "interview_booking_invite" not in booking:
        errors.append("send_invites_missing_invite_template")

    # Wrong / legacy keys must not be used for AI booking flow
    bad = ["interview_confirm", "booking_confirm", "interview_invite"]
    for b in bad:
        if f'template_key="{b}"' in booking or f"template_key='{b}'" in booking:
            errors.append(f"wrong_template_key:{b}")

    return errors


def _db_checks() -> list[str]:
    errors: list[str] = []
    from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
    from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService
    from app.core.database import get_sessionmaker

    for key in INTERVIEW_KEYS:
        if key not in EMAIL_TEMPLATE_KEYS:
            errors.append(f"registry_missing:{key}")
        if key not in SYSTEM_EMAIL_DEFAULTS:
            errors.append(f"defaults_missing:{key}")
        else:
            d = SYSTEM_EMAIL_DEFAULTS[key]
            if not str(d.get("subject") or "").strip() and not str(d.get("body") or "").strip():
                errors.append(f"defaults_empty:{key}")

    with get_sessionmaker()() as db:
        EmailTemplateService.ensure_system_templates(db)
        for key in INTERVIEW_KEYS:
            subj, body, _ = EmailTemplateService.get_send_content(db, key=key)
            if not str(subj).strip() and not str(body).strip():
                errors.append(f"db_send_content_empty:{key}")

    return errors


def main() -> int:
    print("=== Interview email template audit ===\n")
    print("Expected flows (repo):")
    for label, code_path, tpl in EXPECTED_FLOWS:
        print(f"  {label}")
        print(f"    code: {code_path}")
        print(f"    template: {tpl}")
    print()

    code_err = _code_checks()
    print("Code wiring:", "OK" if not code_err else "FAIL")
    for e in code_err:
        print(f"  - {e}")

    try:
        db_err = _db_checks()
        print("DB / defaults:", "OK" if not db_err else "FAIL")
        for e in db_err:
            print(f"  - {e}")
    except Exception as exc:
        print("DB / defaults: FAIL (could not open DB — run on VPS or with local DB)")
        print(f"  - {exc}")
        db_err = ["db_unavailable"]

    print("\nTest scripts:")
    scripts = [
        ("invite", "scripts/send_interview_invite_email_test.py", "interview_booking_invite"),
        ("confirm", "scripts/send_booking_confirm_email_test.py", "interview_booking_confirm"),
    ]
    for name, path, tpl in scripts:
        text = _read(path)
        ok = tpl in text and "send_templated_critical" in text or "send_booking_confirm_email" in text or tpl in text
        print(f"  {path} -> {tpl}: {'OK' if ok else 'CHECK'}")

    all_err = code_err + db_err
    if all_err:
        print(f"\nFAILED ({len(all_err)} issue(s))")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
