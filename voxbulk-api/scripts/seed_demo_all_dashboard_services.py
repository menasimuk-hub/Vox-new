#!/usr/bin/env python3
"""Enable all dashboard modules locally (platform + org) for menu testing.

Usage:
  cd voxbulk-api && python scripts/seed_demo_all_dashboard_services.py
  cd voxbulk-api && python scripts/seed_demo_all_dashboard_services.py --email user@user.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_enabled_services import (
    SERVICE_KEYS,
    merge_admin_allowed_services,
    org_service_maps,
    parse_allowed_services,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)
from app.services.platform_services_settings_service import update_platform_default_allowed

ALL_ON = {key: True for key in SERVICE_KEYS}


def _resolve_org(db, email: str):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"User not found: {email}")
    membership = db.execute(
        select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
    ).scalar_one_or_none()
    if membership is None:
        raise SystemExit(f"No organisation membership for {email}")
    org = db.get(Organisation, membership.org_id)
    if org is None:
        raise SystemExit(f"Organisation not found for {email}")
    return org


def seed(*, email: str) -> None:
    Session = get_sessionmaker()
    with Session() as db:
        update_platform_default_allowed(db, ALL_ON)
        org = _resolve_org(db, email.strip().lower())

        allowed = parse_allowed_services(org.allowed_services_json)
        enabled = parse_enabled_services(org.enabled_services_json)
        new_allowed, _ = merge_admin_allowed_services(allowed, enabled, ALL_ON)
        new_enabled = dict(ALL_ON)
        org.allowed_services_json = serialize_allowed_services(new_allowed)
        org.enabled_services_json = serialize_enabled_services(new_enabled)
        db.add(org)
        db.commit()

        _, _, visible = org_service_maps(org, db)
        visible_names = [k for k, on in visible.items() if on]
        print(f"Platform defaults: all {len(SERVICE_KEYS)} modules ON")
        print(f"Org {org.name!r} ({org.id}): allowed + enabled all ON")
        print(f"Visible in dashboard: {', '.join(visible_names)}")
        print(f"Login as {email} and refresh the dashboard to see all sidebar menus.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable all dashboard modules for local demo")
    parser.add_argument("--email", default="user@user.com", help="Dashboard user email")
    args = parser.parse_args()
    seed(email=args.email)


if __name__ == "__main__":
    main()
