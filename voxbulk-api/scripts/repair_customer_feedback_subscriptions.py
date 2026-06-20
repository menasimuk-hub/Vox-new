#!/usr/bin/env python3
"""Repair Customer Feedback subscription tags, usage periods, and org module flags."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.services.customer_feedback.repair_service import FeedbackSubscriptionRepairService


def _assert_production_database() -> None:
    settings = get_settings()
    url = str(settings.database_url or "")
    env = str(settings.env or "").strip().lower()
    if url.startswith("sqlite:") and env in {"production", "prod", "staging"}:
        print(
            f"ERROR: refusing SQLite in {env}. Run from {API_ROOT} with DATABASE_URL set in .env",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if url.startswith("sqlite:"):
        print(f"WARNING: using SQLite ({url}) — ensure this is intentional for local dev", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Customer Feedback subscriptions")
    parser.add_argument("--org-id", help="Repair a single organisation UUID")
    parser.add_argument("--all", action="store_true", help="Repair every org with a feedback plan subscription")
    args = parser.parse_args()

    if not args.org_id and not args.all:
        parser.error("Pass --org-id UUID or --all")

    _assert_production_database()
    settings = get_settings()
    print(f"Database: {settings.database_url[:48]}…", file=sys.stderr)

    with get_sessionmaker()() as db:
        if args.all:
            result = FeedbackSubscriptionRepairService.repair_all(db)
        else:
            result = FeedbackSubscriptionRepairService.repair_org(db, args.org_id)

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
