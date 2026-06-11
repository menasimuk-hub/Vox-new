#!/usr/bin/env python3
"""
DEV/OPS ONLY — purge billing history and hard-delete dashboard users.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --dry-run \\
    --user-id YOUR-USER-UUID --delete-users --delete-solo-orgs
  .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --apply \\
    --confirm PURGE_TEST_USERS --user-id YOUR-USER-UUID \\
    --delete-users --delete-solo-orgs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.user_hard_delete_service import (
    UserHardDeleteError,
    billing_counts,
    hard_delete_user,
    solo_org_candidate,
)

DEFAULT_USER_IDS = [
    "7444fd4f-0a9d-4f4a-b769-cb9c2e85777f",
    "9045fe68-bb11-409b-a88f-6e32e9bfaeb2",
    "330944d5-9a96-473a-b44e-804e4270d1f0",
    "559549ad-980f-4a51-8dc2-af66b998afd4",
]

CONFIRM_TOKEN = "PURGE_TEST_USERS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge billing + hard-delete test dashboard users (DEV/OPS)")
    parser.add_argument("--user-id", action="append", dest="user_ids", default=[], help="User UUID (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument("--apply", action="store_true", help="Execute deletes")
    parser.add_argument("--confirm", default="", help=f"Required with --apply: {CONFIRM_TOKEN}")
    parser.add_argument("--delete-users", action="store_true", help="Hard-delete user rows")
    parser.add_argument("--delete-solo-orgs", action="store_true", help="Delete sole-member orgs (test)")
    args = parser.parse_args()

    if args.apply and args.confirm != CONFIRM_TOKEN:
        print(f"Refusing --apply without --confirm {CONFIRM_TOKEN}")
        return 2
    if not args.apply:
        args.dry_run = True

    user_ids = list(dict.fromkeys(args.user_ids or DEFAULT_USER_IDS))
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== purge_user_billing_and_accounts ({mode}) ===")
    print(f"users: {len(user_ids)}")
    print(f"delete_users={args.delete_users} delete_solo_orgs={args.delete_solo_orgs}")
    print()

    reports: list[dict[str, Any]] = []
    with get_sessionmaker()() as db:
        for user_id in user_ids:
            print(f"--- {user_id} ---")
            try:
                if args.apply and args.delete_users:
                    report = hard_delete_user(
                        db,
                        user_id,
                        delete_solo_orgs=args.delete_solo_orgs,
                        delete_service_orders=True,
                    )
                    reports.append(report)
                    print(f"  deleted {report.get('email')}")
                else:
                    user = db.get(User, user_id)
                    if user is None:
                        reports.append({"user_id": user_id, "status": "missing"})
                        print("  user not found")
                        continue
                    org_ids = sorted(
                        m.org_id
                        for m in db.execute(
                            select(OrganisationMembership).where(OrganisationMembership.user_id == user_id)
                        ).scalars().all()
                    )
                    for oid in org_ids:
                        print(f"  org {oid}: {billing_counts(db, oid)}")
                    if args.delete_solo_orgs:
                        for oid in org_ids:
                            ok, reason = solo_org_candidate(db, oid, user_id)
                            print(f"    solo org {oid}: deletable={ok} {reason or ''}")
                    reports.append({"user_id": user_id, "status": "ok", "email": user.email})
            except UserHardDeleteError as exc:
                db.rollback()
                print(f"ERROR: {exc}")
                return 1
            except Exception as exc:
                db.rollback()
                print(f"ERROR: {exc}")
                return 1
        if args.apply:
            db.commit()
            print("\nCommitted.")
        else:
            db.rollback()
            print("\nDry-run complete (rolled back).")

    missing = [r for r in reports if r.get("status") == "missing"]
    if missing:
        print(f"\nWARN: {len(missing)} user id(s) not found in database")
        return 1

    print("\nDone.")
    if not args.apply and args.delete_users:
        print(
            f"To execute: .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --apply "
            f"--confirm {CONFIRM_TOKEN} --user-id <uuid> --delete-users --delete-solo-orgs"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
