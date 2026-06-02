#!/usr/bin/env python3
"""Run send_invites for one order (same path as dashboard launch)."""

from __future__ import annotations

import argparse
import json
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test interview send_invites for an order")
    parser.add_argument("order_id", help="Service order UUID")
    parser.add_argument("--force", action="store_true", help="Force resend email")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.models.service_order import ServiceOrder
    from app.services.interview_booking_service import InterviewBookingService

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, args.order_id)
        if order is None:
            print(f"Order not found: {args.order_id}")
            return 1
        result = InterviewBookingService.send_invites(
            db,
            order,
            channels=["email", "whatsapp"],
            force_resend=args.force,
            force_email=True,
        )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("email_sent") else 1


if __name__ == "__main__":
    raise SystemExit(main())
