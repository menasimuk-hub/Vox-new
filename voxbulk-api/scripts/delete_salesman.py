#!/usr/bin/env python3
"""Completely delete a salesman and ALL their data (demo data included), by email.

This is IRREVERSIBLE. It removes:
  - Sales rows: SalesCommission, SalesCustomer, SalesRep
  - The salesman's workspace organisation and everything in it
    (surveys/campaigns, interviews, feedback locations/sessions/responses, wallet,
     billing invoices, memberships, etc.) via hard_delete_user
  - The login user row itself

Usage (from voxbulk-api, project venv):
  python -m scripts.delete_salesman --email salesman02@voxbulk.com --yes

Without --yes it does a dry run and only prints what it would delete.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.user import User
from app.services.user_hard_delete_service import UserHardDeleteError, hard_delete_user


def _resolve_user(db, email: str) -> User:
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"No user found with email {email!r}.")
    return user


def _summarise(db, user: User) -> dict:
    rep = db.execute(select(SalesRep).where(SalesRep.user_id == user.id)).scalar_one_or_none()
    rep_id = rep.id if rep else None
    customers = 0
    commissions = 0
    if rep_id:
        customers = int(
            db.execute(select(func.count()).select_from(SalesCustomer).where(SalesCustomer.sales_rep_id == rep_id)).scalar_one() or 0
        )
        commissions = int(
            db.execute(select(func.count()).select_from(SalesCommission).where(SalesCommission.sales_rep_id == rep_id)).scalar_one() or 0
        )
    org_ids = sorted(
        {m.org_id for m in db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)).scalars().all()}
    )
    return {"rep_id": rep_id, "customers": customers, "commissions": commissions, "org_ids": org_ids}


def _delete_sales_rows(db, rep: SalesRep) -> None:
    db.execute(delete(SalesCommission).where(SalesCommission.sales_rep_id == rep.id))
    db.execute(delete(SalesCustomer).where(SalesCustomer.sales_rep_id == rep.id))
    db.execute(delete(SalesRep).where(SalesRep.id == rep.id))
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Completely delete a salesman and all their data.")
    parser.add_argument("--email", required=True, help="Salesman login email.")
    parser.add_argument("--yes", action="store_true", help="Actually delete (without this it is a dry run).")
    args = parser.parse_args()

    Session = get_sessionmaker()
    db = Session()
    try:
        user = _resolve_user(db, args.email)
        summary = _summarise(db, user)
        print(f"Salesman: {user.email} (user {user.id})")
        print(f"  sales rep:     {summary['rep_id'] or '(none — not a salesman)'}")
        print(f"  customers:     {summary['customers']}")
        print(f"  commissions:   {summary['commissions']}")
        print(f"  organisations: {summary['org_ids'] or '(none)'}")

        if not args.yes:
            print("\nDRY RUN — nothing deleted. Re-run with --yes to permanently delete everything above.")
            return

        rep = db.execute(select(SalesRep).where(SalesRep.user_id == user.id)).scalar_one_or_none()
        if rep is not None:
            _delete_sales_rows(db, rep)

        try:
            report = hard_delete_user(
                db,
                str(user.id),
                delete_solo_orgs=True,
                delete_service_orders=True,
            )
        except UserHardDeleteError as exc:
            db.rollback()
            raise SystemExit(f"Delete blocked: {exc}") from exc

        db.commit()
        print("\nDeleted. Org purge report:")
        for oid, info in (report.get("billing") or {}).items():
            print(f"  org {oid} ({info.get('org_name')}): billing {info.get('deleted')}")
        for entry in report.get("solo_orgs") or []:
            if entry.get("purged"):
                print(f"  org {entry.get('org_id')}: {entry.get('purged')}")
        print("Salesman fully removed.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
