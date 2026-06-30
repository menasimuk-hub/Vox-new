#!/usr/bin/env python3
"""Seed demo data for a salesman workspace, by login email.

Usage (from voxbulk-api, project venv):
  python -m scripts.seed_sales_demo --email salesman1@voxbulk.com
  python -m scripts.seed_sales_demo --email salesman1@voxbulk.com --reset

What it seeds (into the salesman's own workspace org):
  - 20 AI interviews (4 "Advance"/pass, 10 scoring > 50%)
  - 200 WhatsApp survey responses
  - 50 AI-call (phone) survey responses
  - 100 separate "sent" WhatsApp campaigns
  - 3 Customer Feedback QR locations (one named "Demo"), each 100-200 scans/responses
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.demo_account_seed_service import (
    DEFAULT_DEMO_COUNTS,
    DEMO_ACCOUNT_PACK,
    DemoAccountSeedService,
)


def _resolve_user_org(db, email: str) -> tuple[User, str]:
    user = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"No user found with email {email!r}. Create the salesman first in Admin -> Salesmen.")
    membership = db.execute(
        select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
    ).scalar_one_or_none()
    if membership is None:
        raise SystemExit(f"User {email!r} has no organisation membership; cannot seed a workspace.")
    return user, str(membership.org_id)


def _reset_demo(db, org_id: str) -> None:
    """Remove previously-seeded demo rows so the seed can run again cleanly."""
    from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    orders = db.execute(select(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalars().all()
    removed_orders = 0
    for order in orders:
        try:
            cfg = json.loads(order.config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        if cfg.get("demo_account_pack") == DEMO_ACCOUNT_PACK or cfg.get("demo_survey_pack") == DEMO_ACCOUNT_PACK:
            db.execute(
                ServiceOrderRecipient.__table__.delete().where(ServiceOrderRecipient.order_id == order.id)
            )
            db.delete(order)
            removed_orders += 1

    locs = db.execute(select(FeedbackLocation).where(FeedbackLocation.org_id == org_id)).scalars().all()
    removed_locs = 0
    for loc in locs:
        try:
            cfg = json.loads(loc.survey_config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        if cfg.get("demo_account_pack") == DEMO_ACCOUNT_PACK:
            session_ids = db.execute(
                select(FeedbackSession.id).where(FeedbackSession.location_id == loc.id)
            ).scalars().all()
            if session_ids:
                db.execute(FeedbackResponse.__table__.delete().where(FeedbackResponse.session_id.in_(session_ids)))
                db.execute(FeedbackSession.__table__.delete().where(FeedbackSession.location_id == loc.id))
            db.delete(loc)
            removed_locs += 1

    db.commit()
    print(f"Reset: removed {removed_orders} demo order(s) and {removed_locs} demo feedback location(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed salesman demo data by email.")
    parser.add_argument("--email", required=True, help="Salesman login email.")
    parser.add_argument("--reset", action="store_true", help="Remove previously-seeded demo data first.")
    args = parser.parse_args()

    Session = get_sessionmaker()
    db = Session()
    try:
        user, org_id = _resolve_user_org(db, args.email)
        print(f"Seeding demo data for {user.email} (org {org_id})...")
        if args.reset:
            _reset_demo(db, org_id)
        result = DemoAccountSeedService.seed_for_org(
            db, org_id=org_id, user_id=str(user.id), counts=DEFAULT_DEMO_COUNTS
        )
        if result.get("skipped"):
            print("Already seeded — run again with --reset to re-seed.")
        else:
            print("Done:")
            print(f"  interview order:   {result.get('interview_order_id')}")
            print(f"  AI-call survey:    {result.get('ai_survey_order_id')}")
            print(f"  WhatsApp survey:   {result.get('wa_survey_order_id')}")
            print(f"  campaigns:         {len(result.get('campaign_order_ids') or [])}")
            print(f"  feedback locations:{len(result.get('feedback_location_ids') or [])}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
