#!/usr/bin/env python3
"""Backfill usage_metered_at for completed web/phone interview sessions missing plan metering.

Run on VPS:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/backfill_interview_session_usage.py --dry-run
  python3 scripts/backfill_interview_session_usage.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meter historical interview sessions missing usage_metered_at")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.billing_call_minutes import billable_call_minutes
    from app.services.interview_session_billing_service import meter_session_if_needed

    def _loads(raw: str | None) -> dict:
        try:
            data = json.loads(raw or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    metered = 0
    scanned = 0
    with get_sessionmaker()() as db:
        rows = list(
            db.execute(
                select(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.service_code == "interview",
                    ServiceOrderRecipient.status.in_(("completed", "done")),
                )
                .order_by(ServiceOrderRecipient.updated_at.desc())
                .limit(max(1, int(args.limit)))
            ).scalars()
        )
        for recipient in rows:
            scanned += 1
            parsed = _loads(recipient.result_json)
            if parsed.get("usage_metered_at"):
                continue
            bm = int(parsed.get("billable_minutes") or 0)
            if bm <= 0:
                bm = billable_call_minutes(parsed.get("duration_seconds"))
            if bm <= 0:
                continue
            order = db.get(ServiceOrder, recipient.order_id)
            if order is None:
                continue
            if args.dry_run:
                print(
                    f"  would meter order={order.campaign_id or order.id[:8]} "
                    f"recipient={recipient.name or recipient.id[:8]} "
                    f"bm={bm}"
                )
                metered += 1
                continue
            units = meter_session_if_needed(db, order, recipient)
            if units > 0:
                metered += 1
                print(f"  metered {units} min — {order.campaign_id or order.id} / {recipient.name or recipient.id}")

    print(f"\nScanned {scanned} completed recipients; metered {metered}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
