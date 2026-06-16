#!/usr/bin/env python3
"""Repair Customer Feedback subscription tags, usage periods, and org module flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_sessionmaker
from app.services.customer_feedback.repair_service import FeedbackSubscriptionRepairService


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Customer Feedback subscriptions")
    parser.add_argument("--org-id", help="Repair a single organisation UUID")
    parser.add_argument("--all", action="store_true", help="Repair every org with a feedback plan subscription")
    args = parser.parse_args()

    if not args.org_id and not args.all:
        parser.error("Pass --org-id UUID or --all")

    with get_sessionmaker()() as db:
        if args.all:
            result = FeedbackSubscriptionRepairService.repair_all(db)
        else:
            result = FeedbackSubscriptionRepairService.repair_org(db, args.org_id)

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
