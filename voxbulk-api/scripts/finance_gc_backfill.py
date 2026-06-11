#!/usr/bin/env python3
"""Report or backfill GoCardless subscriptions missing external_subscription_id."""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.subscription import Subscription


def main() -> int:
    parser = argparse.ArgumentParser(description="GoCardless subscription backfill report")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument("--apply", action="store_true", help="Attempt mandate-based mandate_id backfill from GC API")
    args = parser.parse_args()

    missing = 0
    with get_sessionmaker()() as db:
        rows = list(
            db.execute(
                select(Subscription).where(
                    Subscription.payment_provider == "gocardless",
                    Subscription.status.in_(["active", "trial", "past_due", "pending_first_payment"]),
                )
            )
            .scalars()
            .all()
        )
        for sub in rows:
            ext = str(sub.external_subscription_id or "").strip()
            mandate = str(sub.mandate_id or "").strip()
            if ext:
                continue
            missing += 1
            print(
                f"MISSING external_subscription_id: sub={sub.id} org={sub.org_id} "
                f"service={sub.service_code} mandate={mandate or '—'} status={sub.status}"
            )
            if args.apply and mandate:
                try:
                    from app.services.gocardless_service import BillingService

                    resolved = BillingService.resolve_org_mandate_id(db, sub.org_id)
                    db.refresh(sub)
                    if str(sub.external_subscription_id or "").strip():
                        print(f"  -> backfilled via mandate lookup: {sub.external_subscription_id}")
                    elif resolved:
                        print(f"  -> mandate resolved={resolved} but no GC subscription id stored")
                except Exception as exc:
                    print(f"  -> lookup failed: {exc}")

    print(f"\nSummary: {missing} active GC subscription(s) missing external_subscription_id")
    if missing and not args.apply:
        print("Run with --apply to attempt mandate-based resolution (manual GC dashboard may still be required).")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
