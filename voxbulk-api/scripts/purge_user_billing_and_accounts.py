#!/usr/bin/env python3
"""
DEV/OPS ONLY — purge billing history and hard-delete dashboard users.

Wipes per-org billing ledger (invoices, subscriptions, wallet, payment events,
refund reviews, usage periods) then optionally hard-deletes user rows.

Does NOT cancel GoCardless/Stripe subscriptions in external providers — cancel
those manually if the account had live mandates.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --dry-run
  .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --apply \\
    --confirm PURGE_TEST_USERS \\
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

from sqlalchemy import delete, func, select, update

from app.core.database import get_sessionmaker
from app.models.billing_invoice import BillingInvoice
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.billing_refund_review import BillingRefundReview
from app.models.credit_note import CreditNote
from app.models.customer_feedback import FeedbackUsagePeriod
from app.models.membership import OrganisationMembership
from app.models.oauth_identity import OAuthIdentity
from app.models.organisation import Organisation
from app.models.org_usage_period import OrgUsagePeriod
from app.models.password_reset_token import PasswordResetToken
from app.models.payment_event import PaymentEvent
from app.models.promo_offer import PromoRedemption
from app.models.subscription import Subscription
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction

DEFAULT_USER_IDS = [
    "7444fd4f-0a9d-4f4a-b769-cb9c2e85777f",
    "9045fe68-bb11-409b-a88f-6e32e9bfaeb2",
    "330944d5-9a96-473a-b44e-804e4270d1f0",
    "559549ad-980f-4a51-8dc2-af66b998afd4",
]

CONFIRM_TOKEN = "PURGE_TEST_USERS"


def _count(db, model, *filters) -> int:
    q = select(func.count()).select_from(model)
    for f in filters:
        q = q.where(f)
    return int(db.execute(q).scalar_one() or 0)


def billing_counts(db, org_id: str) -> dict[str, int]:
    return {
        "billing_refund_reviews": _count(db, BillingRefundReview, BillingRefundReview.org_id == org_id),
        "feedback_usage_periods": _count(db, FeedbackUsagePeriod, FeedbackUsagePeriod.org_id == org_id),
        "credit_notes": _count(db, CreditNote, CreditNote.org_id == org_id),
        "wallet_transactions": _count(db, WalletTransaction, WalletTransaction.org_id == org_id),
        "payment_events": _count(db, PaymentEvent, PaymentEvent.org_id == org_id),
        "billing_invoices": _count(db, BillingInvoice, BillingInvoice.org_id == org_id),
        "subscriptions": _count(db, Subscription, Subscription.org_id == org_id),
        "billing_redirect_flows": _count(db, BillingRedirectFlow, BillingRedirectFlow.org_id == org_id),
        "org_usage_periods": _count(db, OrgUsagePeriod, OrgUsagePeriod.org_id == org_id),
    }


def purge_billing_for_org(db, org_id: str, *, apply: bool) -> dict[str, int]:
    counts = billing_counts(db, org_id)
    if not apply:
        return counts

    db.execute(
        update(Subscription)
        .where(Subscription.org_id == org_id)
        .values(cancellation_support_ticket_id=None)
    )
    for model, col in (
        (BillingRefundReview, BillingRefundReview.org_id),
        (FeedbackUsagePeriod, FeedbackUsagePeriod.org_id),
        (CreditNote, CreditNote.org_id),
        (WalletTransaction, WalletTransaction.org_id),
        (PaymentEvent, PaymentEvent.org_id),
        (BillingInvoice, BillingInvoice.org_id),
        (Subscription, Subscription.org_id),
        (BillingRedirectFlow, BillingRedirectFlow.org_id),
        (OrgUsagePeriod, OrgUsagePeriod.org_id),
    ):
        db.execute(delete(model).where(col == org_id))

    org = db.get(Organisation, org_id)
    if org is not None:
        org.wallet_balance_pence = 0
        org.survey_credits_balance = 0
        org.interview_credits_balance = 0
        org.credit_limit_minor = 0
        org.billing_currency = None
        org.allow_overage = True
        db.add(org)

    return counts


def user_attachment_counts(db, user_id: str) -> dict[str, int]:
    return {
        "memberships": _count(db, OrganisationMembership, OrganisationMembership.user_id == user_id),
        "password_reset_tokens": _count(db, PasswordResetToken, PasswordResetToken.user_id == user_id),
        "oauth_identities": _count(db, OAuthIdentity, OAuthIdentity.user_id == user_id),
        "billing_redirect_flows": _count(db, BillingRedirectFlow, BillingRedirectFlow.user_id == user_id),
        "promo_redemptions": _count(db, PromoRedemption, PromoRedemption.user_id == user_id),
    }


def delete_user_row(db, user_id: str, *, apply: bool) -> None:
    if not apply:
        return
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    db.execute(delete(OAuthIdentity).where(OAuthIdentity.user_id == user_id))
    db.execute(delete(BillingRedirectFlow).where(BillingRedirectFlow.user_id == user_id))
    db.execute(delete(PromoRedemption).where(PromoRedemption.user_id == user_id))
    db.execute(delete(OrganisationMembership).where(OrganisationMembership.user_id == user_id))
    user = db.get(User, user_id)
    if user is not None:
        db.delete(user)


def solo_org_candidate(db, org_id: str, user_id: str) -> tuple[bool, str | None]:
    members = list(
        db.execute(select(OrganisationMembership).where(OrganisationMembership.org_id == org_id)).scalars().all()
    )
    if len(members) != 1 or members[0].user_id != user_id:
        return False, f"org has {len(members)} member(s)"
    from app.models.service_order import ServiceOrder

    orders = int(
        db.execute(select(func.count()).select_from(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalar_one()
        or 0
    )
    if orders:
        return False, f"org has {orders} service_order row(s) — delete manually or use account archive flow"
    return True, None


def delete_solo_org(db, org_id: str, *, apply: bool) -> bool:
    if not apply:
        return True
    org = db.get(Organisation, org_id)
    if org is None:
        return False
    db.delete(org)
    return True


def process_user(
    db,
    user_id: str,
    *,
    apply: bool,
    delete_users: bool,
    delete_solo_orgs: bool,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        return {"user_id": user_id, "status": "missing", "email": None}

    memberships = list(
        db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user_id)).scalars().all()
    )
    org_ids = sorted({m.org_id for m in memberships})
    report: dict[str, Any] = {
        "user_id": user_id,
        "status": "ok",
        "email": user.email,
        "org_ids": org_ids,
        "billing": {},
        "user_attachments": user_attachment_counts(db, user_id),
        "solo_orgs": [],
    }

    for org_id in org_ids:
        org = db.get(Organisation, org_id)
        org_name = org.name if org else "?"
        counts = purge_billing_for_org(db, org_id, apply=apply)
        report["billing"][org_id] = {"org_name": org_name, "deleted": counts}
        print(f"  org {org_id} ({org_name}): {counts}")

        if delete_solo_orgs:
            ok, reason = solo_org_candidate(db, org_id, user_id)
            entry = {"org_id": org_id, "org_name": org_name, "deletable": ok, "reason": reason}
            report["solo_orgs"].append(entry)
            if ok:
                delete_solo_org(db, org_id, apply=apply)
                print(f"    -> solo org marked for deletion: {org_name}")
            elif reason:
                print(f"    -> solo org skipped: {reason}")

    if delete_users:
        delete_user_row(db, user_id, apply=apply)
        print(f"  user {user.email} ({user_id}) {'deleted' if apply else 'would delete'}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge billing + hard-delete test dashboard users (DEV/OPS)")
    parser.add_argument(
        "--user-id",
        action="append",
        dest="user_ids",
        default=[],
        help="User UUID (repeatable). Defaults to built-in test list when omitted.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument("--apply", action="store_true", help="Execute deletes")
    parser.add_argument("--confirm", default="", help=f"Required with --apply: {CONFIRM_TOKEN}")
    parser.add_argument("--delete-users", action="store_true", help="Hard-delete users rows after billing purge")
    parser.add_argument(
        "--delete-solo-orgs",
        action="store_true",
        help="Delete organisation when user is sole member and org has no service_orders",
    )
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
                reports.append(
                    process_user(
                        db,
                        user_id,
                        apply=args.apply,
                        delete_users=args.delete_users,
                        delete_solo_orgs=args.delete_solo_orgs,
                    )
                )
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
    if not args.apply:
        print(
            f"To execute: .venv/bin/python3 scripts/purge_user_billing_and_accounts.py --apply "
            f"--confirm {CONFIRM_TOKEN} --delete-users --delete-solo-orgs"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
