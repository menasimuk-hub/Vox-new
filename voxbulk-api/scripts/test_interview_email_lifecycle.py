#!/usr/bin/env python3
"""Send every interview lifecycle email to one inbox and (optionally) verify arrival.

This sends REAL email through the same path the app uses (CareerEmailService ->
platform SMTP, From = the careers mailbox). Run it on the VPS where the API/DB live:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/test_interview_email_lifecycle.py --to careers@voxbulk.com --verify-imap

What it does:
  1. Renders + sends all six interview lifecycle templates to --to:
       interview_booking_invite, interview_booking_confirm, interview_booking_reminder,
       interview_thank_you, interview_missed_call_followup, interview_meeting_missed
     Each subject is tagged with a unique run id so we can find them again.
  2. With --verify-imap: waits, then logs into the careers mailbox over IMAP and
     reports which of the six tagged subjects actually landed in the inbox.

Honesty note: this confirms SMTP accepted the message (send step) and, with
--verify-imap, that it was delivered to the careers mailbox itself. Delivery to a
DIFFERENT external inbox can still be affected by that provider's spam filtering.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timedelta

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)

# A marker put in every subject so the IMAP verify step can find exactly this run.
RUN_TAG = f"VBTEST-{uuid.uuid4().hex[:8].upper()}"


def _sample_variables() -> dict[str, str]:
    """Fill every placeholder used across the six interview templates."""
    start = datetime.utcnow() + timedelta(hours=1)
    date_line = start.strftime("%A %d %B %Y")
    time_line = start.strftime("%H:%M")
    booking_url = "https://voxbulk.com/book/TEST-TOKEN"
    meeting_url = "https://voxbulk.com/meet/TEST-TOKEN"
    meeting_link_html = (
        f'<p style="margin:16px 0;"><a href="{meeting_url}" '
        f'style="display:inline-block;padding:12px 18px;background:#1a2d5c;color:#fff;'
        f'text-decoration:none;border-radius:8px;font-weight:600;">Join online meeting</a></p>'
    )
    return {
        "candidate_name": "Test Candidate",
        "first_name": "Test",
        "role": "Lifecycle Email Test",
        "company_name": "VOXBULK",
        "org_name": "VOXBULK",
        "interview_date": date_line,
        "interview_time": time_line,
        "interview_channel_note": "This is a workflow test email — no action needed.",
        "meeting_link_html": meeting_link_html,
        "meeting_url": meeting_url,
        "calendar_links_html": "",
        "calendar_ics_url": "",
        "booking_url": booking_url,
        "followup_message": "This is a workflow test of the missed-call follow-up email.",
        "current_slot": f"{date_line} at {time_line}",
        "reschedule_url": booking_url,
    }


# (template_key, human label) for every email in the interview lifecycle.
LIFECYCLE_TEMPLATES: list[tuple[str, str]] = [
    ("interview_booking_invite", "Invitation"),
    ("interview_booking_confirm", "Booking confirmation"),
    ("interview_booking_reminder", "Reminder"),
    ("interview_thank_you", "Thank-you (completed)"),
    ("interview_missed_call_followup", "Missed call follow-up"),
    ("interview_meeting_missed", "Missed online meeting"),
]


def _send_all(db, to_email: str) -> list[dict]:
    from app.services.career_email_service import (
        CareerEmailService,
        careers_from_address,
        interview_email_delivery_status,
        _render_interview_template,
    )

    status = interview_email_delivery_status(db)
    from_name, from_email = careers_from_address(db)
    print("=== SMTP / sender ===")
    print(f"can_send_email   {status.get('can_send_email')}")
    print(f"smtp_configured  {status.get('smtp_configured')}  enabled={status.get('smtp_enabled')}")
    if status.get("smtp_missing_fields"):
        print(f"missing_fields   {', '.join(status['smtp_missing_fields'])}")
    print(f"from             {from_name} <{from_email}>")
    print(f"to               {to_email}")
    print(f"run_tag          {RUN_TAG}")
    print()

    if not status.get("can_send_email"):
        print("ABORT: SMTP is not ready (configure/enable it in Admin -> Email). Nothing sent.")
        return []

    variables = _sample_variables()
    results: list[dict] = []
    print("=== Sending ===")
    for template_key, label in LIFECYCLE_TEMPLATES:
        # Tag the rendered subject so IMAP verify can find exactly this message.
        rendered = _render_interview_template(db, template_key=template_key, variables=variables)
        base_subject = rendered[0] if rendered else template_key
        tagged_subject = f"[{RUN_TAG}] {base_subject}"
        body = rendered[1] if rendered else f"Test body for {template_key}"
        try:
            CareerEmailService.send(db, to_email=to_email, subject=tagged_subject, body=body)
            ok, err = True, None
        except Exception as exc:  # noqa: BLE001 - report any send failure per template
            ok, err = False, str(exc)
        results.append(
            {"template_key": template_key, "label": label, "subject": tagged_subject, "ok": ok, "error": err}
        )
        mark = "OK " if ok else "ERR"
        print(f"  [{mark}] {label:<26} {template_key}")
        if not ok:
            print(f"         -> {err}")
    print()
    sent_ok = sum(1 for r in results if r["ok"])
    print(f"Sent {sent_ok}/{len(results)} lifecycle emails to {to_email}.")
    return results


def _verify_imap(db, results: list[dict], *, wait_seconds: int, attempts: int) -> None:
    import imaplib

    from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
    from app.services.career_mailbox_sync_service import _connect_imap

    print()
    print("=== IMAP verify (careers mailbox) ===")
    row = CareerMailboxSettingsService.get_row(db)
    configured, missing = CareerMailboxSettingsService.compute_status(row)
    if not configured:
        print(f"SKIP: career mailbox IMAP not configured (missing: {', '.join(missing)}).")
        print("Configure it in Admin -> Integrations -> Career mailbox, or check the inbox manually.")
        return
    password = CareerMailboxSettingsService.get_decrypted_password(db)
    if not password:
        print("SKIP: career mailbox password not set.")
        return
    user = (row.imap_username or row.mailbox_email or "").strip()

    expected = {r["subject"] for r in results if r["ok"]}
    if not expected:
        print("Nothing was sent OK, so nothing to verify.")
        return

    found: set[str] = set()
    for attempt in range(1, max(1, attempts) + 1):
        print(f"  attempt {attempt}/{attempts}: waiting {wait_seconds}s for delivery...")
        time.sleep(max(0, wait_seconds))
        try:
            conn = _connect_imap(row)
            conn.login(user, password)
            conn.select("INBOX")
            # Search by our unique run tag; it appears in every subject we sent.
            typ, data = conn.search(None, "SUBJECT", f'"{RUN_TAG}"')
            ids = (data[0] or b"").split() if typ == "OK" else []
            for num in ids:
                ftyp, fdata = conn.fetch(num, "(BODY[HEADER.FIELDS (SUBJECT)])")
                if ftyp != "OK" or not fdata:
                    continue
                raw = b"".join(part[1] for part in fdata if isinstance(part, tuple) and part[1])
                subj_line = raw.decode("utf-8", "ignore")
                for subject in expected:
                    # Mail servers may fold/encode subjects; match on the run tag + key fragment.
                    if RUN_TAG in subj_line and subject.split("] ", 1)[-1][:24] in subj_line:
                        found.add(subject)
            conn.logout()
        except Exception as exc:  # noqa: BLE001 - report and retry
            print(f"    IMAP error: {exc}")
        if expected.issubset(found):
            break

    print()
    print("=== Verify result ===")
    for r in results:
        if not r["ok"]:
            print(f"  [not sent] {r['label']}")
            continue
        mark = "ARRIVED" if r["subject"] in found else "MISSING"
        print(f"  [{mark}] {r['label']}")
    print()
    print(f"Delivered {len(found)}/{len(expected)} sent emails to the careers mailbox.")
    if not expected.issubset(found):
        print(
            "MISSING ones were accepted by SMTP but not seen in INBOX yet — check Spam/Junk, "
            "allow more time (raise --imap-wait/--imap-attempts), or confirm SPF/DKIM/DMARC for the From domain."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Send + verify all interview lifecycle emails")
    parser.add_argument("--to", default="careers@voxbulk.com", help="Recipient inbox (default careers@voxbulk.com)")
    parser.add_argument("--verify-imap", action="store_true", help="After sending, check the careers mailbox over IMAP")
    parser.add_argument("--imap-wait", type=int, default=20, help="Seconds to wait between IMAP checks (default 20)")
    parser.add_argument("--imap-attempts", type=int, default=6, help="Number of IMAP check attempts (default 6)")
    args = parser.parse_args()

    to_email = str(args.to or "").strip().lower()
    if "@" not in to_email:
        print(f"Invalid --to address: {args.to!r}")
        return 2

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        results = _send_all(db, to_email)
        if not results:
            return 1
        if args.verify_imap:
            # Only IMAP-verify when sending to the careers mailbox itself.
            from app.services.career_mailbox_settings_service import CareerMailboxSettingsService

            mailbox = str(CareerMailboxSettingsService.get_row(db).mailbox_email or "").strip().lower()
            if mailbox and to_email != mailbox:
                print()
                print(
                    f"Note: --verify-imap reads the careers mailbox ({mailbox}); "
                    f"you sent to {to_email}, so check that inbox manually instead."
                )
            else:
                _verify_imap(db, results, wait_seconds=args.imap_wait, attempts=args.imap_attempts)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
