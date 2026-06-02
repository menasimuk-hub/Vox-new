#!/usr/bin/env python3
"""Send one interview_booking_invite via CareerEmailService (same path as launch)."""

from __future__ import annotations

import argparse
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test interview invite email on VPS")
    parser.add_argument("--to", required=True, help="Recipient inbox")
    parser.add_argument("--booking-url", default="https://dashboard.voxbulk.com/book/test-token")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.career_email_service import CareerEmailService, interview_email_delivery_status

    with get_sessionmaker()() as db:
        print("Delivery:", interview_email_delivery_status(db))
        ok, err = CareerEmailService.send_templated_critical(
            db,
            template_key="interview_booking_invite",
            to_email=args.to,
            variables={
                "candidate_name": "Test Candidate",
                "role": "Test Role",
                "company_name": "Test Company",
                "booking_url": args.booking_url,
            },
        )
    if ok:
        print(f"OK — invite email sent to {args.to}")
        return 0
    print(f"FAIL — {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
