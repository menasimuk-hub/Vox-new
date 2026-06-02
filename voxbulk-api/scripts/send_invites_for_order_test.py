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


def resolve_order(db, ref: str):
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder

    key = str(ref or "").strip()
    if not key:
        return None
    order = db.get(ServiceOrder, key)
    if order is not None:
        return order
    return db.execute(
        select(ServiceOrder).where(ServiceOrder.campaign_id == key).limit(1)
    ).scalar_one_or_none()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test interview send_invites for an order")
    parser.add_argument(
        "order_ref",
        help="Service order UUID or dashboard campaign id (e.g. VB-CMP-BD574F77)",
    )
    parser.add_argument("--force", action="store_true", help="Force resend email")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.interview_booking_service import InterviewBookingService

    with get_sessionmaker()() as db:
        order = resolve_order(db, args.order_ref)
        if order is None:
            print(f"Order not found: {args.order_ref}")
            print("Use the campaign id from the dashboard (VB-CMP-...) or the internal order UUID.")
            return 1
        print(f"Order id={order.id} campaign_id={order.campaign_id} status={order.status}")
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
