"""Create a demo public booking link for local QA."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import booking_public_origin, booking_url_for_token

DEMO_TOKEN = "demo-voxbulk-booking"


def main() -> None:
    Session = get_sessionmaker()
    with Session() as db:
        order = db.execute(
            select(ServiceOrder)
            .where(ServiceOrder.service_code == "interview")
            .order_by(ServiceOrder.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if order is None:
            print("No interview orders found — run seed_dummy_interview.py first")
            sys.exit(1)

        recipient = db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number.asc())
            .limit(1)
        ).scalar_one_or_none()
        if recipient is None:
            print(f"Order {order.id} has no recipients")
            sys.exit(1)

        now = datetime.utcnow()
        if not order.scheduled_start_at:
            order.scheduled_start_at = now + timedelta(days=1)
        if not order.scheduled_end_at:
            order.scheduled_end_at = order.scheduled_start_at + timedelta(days=2)
        db.add(order)

        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == DEMO_TOKEN).limit(1)
        ).scalar_one_or_none()
        if row is None:
            row = InterviewBookingToken(
                order_id=order.id,
                recipient_id=recipient.id,
                org_id=order.org_id,
                token=DEMO_TOKEN,
                expires_at=order.scheduled_end_at,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.order_id = order.id
            row.recipient_id = recipient.id
            row.org_id = order.org_id
            row.expires_at = order.scheduled_end_at
            row.booked_start_at = None
            row.booked_end_at = None
            row.updated_at = now
            db.add(row)

        db.commit()
        url = booking_url_for_token(DEMO_TOKEN)
        print(f"Campaign:  {order.title}")
        print(f"Order ID:  {order.id}")
        print(f"Candidate: {recipient.name}")
        print(f"Token:     {DEMO_TOKEN}")
        print(f"Booking:   {url}")
        print(f"API base:  {booking_public_origin()}")


if __name__ == "__main__":
    main()
