#!/usr/bin/env python3
"""Send one interview_booking_confirm email (same template path as after candidate books)."""

from __future__ import annotations

import argparse
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test interview_booking_confirm template on VPS")
    parser.add_argument("--to", required=True, help="Recipient inbox")
    parser.add_argument(
        "--plain-fallback-only",
        action="store_true",
        help="Only send plain backup (not the admin template)",
    )
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.career_email_service import CareerEmailService, interview_email_delivery_status
    from app.services.email_template_service import EmailTemplateService

    variables = {
        "candidate_name": "Test Candidate",
        "role": "Test Role",
        "company_name": "Test Company",
        "interview_date": "Wed 4 Jun 2026",
        "interview_time": "14:30",
        "calendar_links_html": "",
        "calendar_ics_url": "https://api.voxbulk.com/public/interview-booking/test-token/calendar.ics",
    }

    with get_sessionmaker()() as db:
        status = interview_email_delivery_status(db)
        print("Delivery:", status)
        subj, body, enabled = EmailTemplateService.get_send_content(db, key="interview_booking_confirm")
        print(f"Template interview_booking_confirm: enabled={enabled} subject_len={len(subj)} body_len={len(body)}")
        if not subj.strip() and not body.strip():
            print("WARN — template empty in DB; send will use system default or fail")

        if args.plain_fallback_only:
            ok, err = CareerEmailService.send_booking_confirmation_fallback(
                db, to_email=args.to, variables=variables
            )
            channel = "plain_fallback"
        else:
            ok, err, channel = CareerEmailService.send_booking_confirm_email(
                db, to_email=args.to, variables=variables
            )
    if ok:
        print(f"OK — sent via {channel} to {args.to}")
        if channel != "interview_booking_confirm":
            print("NOTE — did NOT use interview_booking_confirm; check template/SMTP HTML errors above")
        return 0
    print(f"FAIL — {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
