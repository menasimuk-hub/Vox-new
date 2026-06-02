#!/usr/bin/env python3
"""Send one plain booking confirmation (same path as after candidate books a slot)."""

from __future__ import annotations

import argparse
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test booking confirmation email on VPS")
    parser.add_argument("--to", required=True, help="Recipient inbox")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.career_email_service import CareerEmailService, interview_email_delivery_status

    variables = {
        "candidate_name": "Test Candidate",
        "role": "Test Role",
        "company_name": "Test Company",
        "interview_date": "Wed 4 Jun 2026",
        "interview_time": "14:30",
        "calendar_ics_url": "https://dashboard.voxbulk.com/book/test-token/calendar.ics",
    }

    with get_sessionmaker()() as db:
        status = interview_email_delivery_status(db)
        print("Delivery:", status)
        ok, err = CareerEmailService.send_booking_confirmation_fallback(
            db,
            to_email=args.to,
            variables=variables,
        )
    if ok:
        print(f"OK — confirmation email sent to {args.to}")
        return 0
    print(f"FAIL — {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
