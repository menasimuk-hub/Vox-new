"""Detect billing anomalies for admin operations visibility."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.billing_refund_review import BillingRefundReview
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.models.subscription import Subscription
from app.services.billing_currency import resolve_org_currency
from app.services.subscription_cancellation_service import CANCELLATION_SCHEDULED

_STUCK_DD_HOURS = 48


class BillingExceptionsService:
    @staticmethod
    def list_exceptions(db: Session, *, limit: int = 200) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 200), 500))
        now = datetime.utcnow()
        out: list[dict[str, Any]] = []

        subs = list(
            db.execute(
                select(Subscription, Organisation, Plan)
                .join(Organisation, Organisation.id == Subscription.org_id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.status.in_(("active", "trial", "past_due")))
                .order_by(Subscription.updated_at.desc())
                .limit(cap * 2)
            ).all()
        )

        for sub, org, plan in subs:
            if sub.next_billing_date is None and sub.current_period_end is None:
                out.append(
                    {
                        "kind": "missing_next_billing_date",
                        "severity": "warning",
                        "org_id": org.id,
                        "org_name": org.name,
                        "subscription_id": sub.id,
                        "detail": "Active subscription has no current period end or next billing date.",
                    }
                )
            elif sub.next_billing_date is None and sub.current_period_end and str(sub.status).lower() in {"active", "trial"}:
                out.append(
                    {
                        "kind": "missing_next_billing_date",
                        "severity": "warning",
                        "org_id": org.id,
                        "org_name": org.name,
                        "subscription_id": sub.id,
                        "detail": "Subscription period end exists but next_billing_date is not synced.",
                    }
                )

            if (
                str(sub.cancellation_status or "").lower() == CANCELLATION_SCHEDULED
                and str(sub.status or "").lower() in {"active", "trial"}
                and sub.cancellation_effective_at
                and sub.cancellation_effective_at < now
            ):
                out.append(
                    {
                        "kind": "canceled_but_not_closed",
                        "severity": "error",
                        "org_id": org.id,
                        "org_name": org.name,
                        "subscription_id": sub.id,
                        "detail": "Cancellation effective date passed but subscription still active.",
                    }
                )

            org_currency = resolve_org_currency(db, org)
            sub_currency = (sub.billing_currency or org_currency or "GBP").upper()
            if org_currency and sub_currency and org_currency.upper() != sub_currency.upper():
                out.append(
                    {
                        "kind": "currency_mismatch",
                        "severity": "warning",
                        "org_id": org.id,
                        "org_name": org.name,
                        "subscription_id": sub.id,
                        "detail": f"Org billing currency {org_currency} vs subscription snapshot {sub_currency}.",
                    }
                )

        failed_invoices = list(
            db.execute(
                select(BillingInvoice, Organisation)
                .join(Organisation, Organisation.id == BillingInvoice.org_id)
                .where(BillingInvoice.status.in_(("failed", "past_due")))
                .order_by(BillingInvoice.created_at.desc())
                .limit(50)
            ).all()
        )
        for inv, org in failed_invoices:
            out.append(
                {
                    "kind": "failed_renewal",
                    "severity": "error",
                    "org_id": org.id,
                    "org_name": org.name,
                    "invoice_id": inv.id,
                    "detail": f"Invoice {inv.invoice_number or inv.id} status {inv.status}.",
                }
            )

        pending_reviews = list(
            db.execute(
                select(BillingRefundReview, Organisation)
                .join(Organisation, Organisation.id == BillingRefundReview.org_id)
                .where(BillingRefundReview.review_status.in_(("pending", "under_review", "approved")))
                .order_by(BillingRefundReview.requested_at.asc())
                .limit(50)
            ).all()
        )
        for review, org in pending_reviews:
            out.append(
                {
                    "kind": "pending_refund_queue",
                    "severity": "info",
                    "org_id": org.id,
                    "org_name": org.name,
                    "refund_review_id": review.id,
                    "detail": f"Refund review {review.review_status} since {review.requested_at.date().isoformat()}.",
                }
            )

        stuck_cutoff = now - timedelta(hours=_STUCK_DD_HOURS)
        stuck_invoices = list(
            db.execute(
                select(BillingInvoice, Organisation)
                .join(Organisation, Organisation.id == BillingInvoice.org_id)
                .where(
                    BillingInvoice.status == "collecting",
                    BillingInvoice.dd_payment_id.isnot(None),
                    BillingInvoice.created_at < stuck_cutoff,
                )
                .order_by(BillingInvoice.created_at.asc())
                .limit(50)
            ).all()
        )
        for inv, org in stuck_invoices:
            out.append(
                {
                    "kind": "stuck_dd_collecting",
                    "severity": "error",
                    "org_id": org.id,
                    "org_name": org.name,
                    "invoice_id": inv.id,
                    "detail": f"Invoice {inv.invoice_number or inv.id} collecting >{_STUCK_DD_HOURS}h (DD {inv.dd_payment_id}).",
                }
            )

        for sub, org, plan in subs:
            org_currency = resolve_org_currency(db, org)
            price_row = db.execute(
                select(PlanPrice).where(
                    PlanPrice.plan_id == plan.id,
                    PlanPrice.currency == org_currency,
                    PlanPrice.is_active.is_(True),
                )
            ).scalar_one_or_none()
            monthly = price_row.monthly_price_minor if price_row else None
            if monthly is None and not getattr(plan, "price_gbp_pence", None):
                out.append(
                    {
                        "kind": "missing_plan_price",
                        "severity": "warning",
                        "org_id": org.id,
                        "org_name": org.name,
                        "subscription_id": sub.id,
                        "detail": f"No active {org_currency} plan price for {plan.code or plan.name}.",
                    }
                )

        return out[:cap]

    @staticmethod
    def summary(db: Session) -> dict[str, int]:
        items = BillingExceptionsService.list_exceptions(db, limit=500)
        counts: dict[str, int] = {}
        for item in items:
            kind = item.get("kind") or "other"
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "total": len(items),
            **counts,
        }
