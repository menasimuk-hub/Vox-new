"""Admin finance queries: subscription billing snapshots, ledger, refunds, payment events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.billing_refund_review import BillingRefundReview
from app.models.organisation import Organisation
from app.models.payment_event import PaymentEvent
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.payment_event_service import PaymentEventService
from app.services.plan_price_service import PlanPriceService
from app.services.subscription_cancellation_service import (
    CANCELLATION_SCHEDULED,
    CANCEL_TYPE_PERIOD_END,
    SubscriptionCancellationService,
)
from app.services.wallet_service import WalletService


def normalize_refund_status(status: str | None) -> str:
    s = str(status or "").strip().lower()
    if s == "completed":
        return "processed"
    if s == "approved":
        return "approved"
    if s == "rejected":
        return "rejected"
    if s == "failed":
        return "failed"
    if s == "under_review":
        return "under_review"
    return s or "pending"


class BillingFinanceService:
    @staticmethod
    def _tax_snapshot(db: Session, org: Organisation) -> tuple[str | None, float | None]:
        from app.services.invoice_service import InvoiceService

        code = (org.country_code or "GB").strip().upper()[:2] or None
        if not code:
            return None, None
        try:
            rate = float(InvoiceService.effective_vat_rate(db, country_code=code))
        except Exception:
            rate = None
        return code, rate

    @staticmethod
    def sync_subscription_billing_fields(
        db: Session,
        sub: Subscription,
        *,
        org: Organisation | None = None,
        plan: Plan | None = None,
        commit: bool = True,
    ) -> Subscription:
        org = org or db.get(Organisation, sub.org_id)
        plan = plan or db.get(Plan, sub.plan_id)
        cancel_status = str(sub.cancellation_status or "none").lower()
        cancel_type = str(sub.cancellation_type or "").lower()
        sub.cancel_at_period_end = cancel_status == CANCELLATION_SCHEDULED and cancel_type == CANCEL_TYPE_PERIOD_END

        effective = SubscriptionCancellationService.effective_status(sub)
        if effective in {"active", "trial", "past_due"}:
            if sub.cancel_at_period_end and sub.cancellation_effective_at:
                sub.next_billing_date = sub.cancellation_effective_at
            elif not sub.cancel_at_period_end:
                sub.next_billing_date = sub.current_period_end
            else:
                sub.next_billing_date = sub.current_period_end
        else:
            sub.next_billing_date = None

        if org and plan:
            currency = resolve_org_currency(db, org)
            tax_code, tax_rate = BillingFinanceService._tax_snapshot(db, org)
            sub.billing_currency = currency
            sub.tax_country_code = tax_code
            sub.tax_rate_percent = tax_rate
            if sub.cancel_at_period_end:
                sub.amount_next_payment_minor = 0
            elif sub.next_billing_date:
                _currency, sub.amount_next_payment_minor = PlanPriceService.monthly_minor_for_org(db, org, plan)
        db.add(sub)
        if commit:
            db.commit()
            db.refresh(sub)
        return sub

    @staticmethod
    def subscription_finance_dict(
        db: Session,
        sub: Subscription,
        *,
        org: Organisation | None = None,
        plan: Plan | None = None,
    ) -> dict[str, Any]:
        org = org or db.get(Organisation, sub.org_id)
        plan = plan or db.get(Plan, sub.plan_id)
        pending = db.get(Plan, sub.pending_plan_id) if sub.pending_plan_id else None
        currency = resolve_org_currency(db, org) if org else "GBP"
        amount_minor = int(sub.amount_next_payment_minor or 0)
        if not amount_minor and plan and org and not sub.cancel_at_period_end:
            _currency, amount_minor = PlanPriceService.monthly_minor_for_org(db, org, plan)
        next_billing = sub.next_billing_date
        if not next_billing and sub.cancel_at_period_end and sub.cancellation_effective_at:
            next_billing = sub.cancellation_effective_at
        return {
            "subscription_id": sub.id,
            "org_id": sub.org_id,
            "status": sub.status,
            "plan_code": plan.code if plan else None,
            "plan_name": plan.name if plan else None,
            "pending_plan_code": pending.code if pending else None,
            "pending_plan_name": pending.name if pending else None,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "next_billing_date": next_billing.isoformat() if next_billing else None,
            "amount_next_payment_minor": amount_minor,
            "amount_next_payment_display": (
                "No renewal (cancel scheduled)" if sub.cancel_at_period_end
                else (money_display(amount_minor, currency) if amount_minor else None)
            ),
            "billing_currency": sub.billing_currency or currency,
            "tax_rate_percent": float(sub.tax_rate_percent) if sub.tax_rate_percent is not None else None,
            "tax_country_code": sub.tax_country_code,
            "cancel_at_period_end": bool(sub.cancel_at_period_end),
            "cancellation_status": sub.cancellation_status,
            "mandate_status": sub.mandate_status,
            "payment_provider": sub.payment_provider,
        }

    @staticmethod
    def upgrade_preview(
        db: Session,
        org_id: str,
        *,
        new_plan_code: str,
    ) -> dict[str, Any]:
        from app.models.plan import Plan

        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        sub = SubscriptionCancellationService.get_subscription(db, org_id)
        if sub is None:
            raise ValueError("No subscription found")
        old_plan = db.get(Plan, sub.plan_id)
        new_plan = db.execute(select(Plan).where(Plan.code == new_plan_code.strip().lower())).scalar_one_or_none()
        if new_plan is None:
            raise ValueError("Plan not found")
        from app.services.billing_lifecycle_service import BillingLifecycleService

        pro_rata = BillingLifecycleService.calculate_pro_rata_minor(
            db, org=org, sub=sub, old_plan=old_plan, new_plan=new_plan
        )
        currency, new_monthly = PlanPriceService.monthly_minor_for_org(db, org, new_plan)
        return {
            "org_id": org_id,
            "current_plan_code": old_plan.code if old_plan else None,
            "new_plan_code": new_plan.code,
            "new_plan_name": new_plan.name,
            "pro_rata_minor": pro_rata,
            "pro_rata_display": money_display(pro_rata, currency),
            "new_monthly_minor": new_monthly,
            "new_monthly_display": money_display(new_monthly, currency),
            "currency": currency,
            "pending_plan_id": sub.pending_plan_id,
        }

    @staticmethod
    def cancellation_preview(db: Session, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        sub = SubscriptionCancellationService.get_subscription(db, org_id)
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id) if sub else None
        refund_review = SubscriptionCancellationService.get_open_refund_review(db, org_id) if sub else None
        payload = SubscriptionCancellationService.cancellation_dict(
            db, org, sub, plan, refund_review=refund_review
        )
        if sub:
            payload["subscription_finance"] = BillingFinanceService.subscription_finance_dict(db, sub, org=org, plan=plan)
        return payload

    @staticmethod
    def list_wallet_ledger(
        db: Session,
        *,
        limit: int = 200,
        org_id: str | None = None,
        kind: str | None = None,
        direction: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 200), 500))
        q = (
            select(WalletTransaction, Organisation)
            .join(Organisation, Organisation.id == WalletTransaction.org_id)
        )
        if org_id:
            q = q.where(WalletTransaction.org_id == org_id)
        if kind:
            q = q.where(WalletTransaction.kind == str(kind).strip().lower())
        if direction:
            q = q.where(WalletTransaction.direction == str(direction).strip().lower())
        if search:
            term = f"%{str(search).strip()}%"
            q = q.where(
                or_(
                    Organisation.name.ilike(term),
                    Organisation.contact_email.ilike(term),
                    WalletTransaction.provider_reference.ilike(term),
                    WalletTransaction.description.ilike(term),
                )
            )
        rows = list(db.execute(q.order_by(WalletTransaction.created_at.desc()).limit(cap)).all())
        out: list[dict[str, Any]] = []
        for tx, org in rows:
            item = WalletService.transaction_to_dict(tx)
            item["org_id"] = org.id
            item["org_name"] = org.name
            item["org_email"] = org.contact_email
            out.append(item)
        return out

    @staticmethod
    def list_payment_events(
        db: Session,
        *,
        limit: int = 200,
        provider: str | None = None,
        status: str | None = None,
        org_id: str | None = None,
        event_kind: str | None = None,
        duplicates_only: bool = False,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 200), 500))
        q = select(PaymentEvent, Organisation).join(
            Organisation, Organisation.id == PaymentEvent.org_id
        )
        if provider:
            q = q.where(PaymentEvent.provider == str(provider).strip().lower())
        if status:
            q = q.where(PaymentEvent.status == str(status).strip().lower())
        if org_id:
            q = q.where(PaymentEvent.org_id == org_id)
        if event_kind:
            q = q.where(PaymentEvent.event_kind == str(event_kind).strip().lower())
        rows = list(db.execute(q.order_by(PaymentEvent.created_at.desc()).limit(cap)).all())

        dup_keys: set[tuple[str, str]] = set()
        if duplicates_only:
            dup_rows = db.execute(
                select(PaymentEvent.provider, PaymentEvent.external_event_id)
                .group_by(PaymentEvent.provider, PaymentEvent.external_event_id)
                .having(func.count() > 1)
            ).all()
            dup_keys = {(r[0], r[1]) for r in dup_rows}

        out: list[dict[str, Any]] = []
        for ev, org in rows:
            if duplicates_only and (ev.provider, ev.external_event_id) not in dup_keys:
                continue
            item = PaymentEventService.event_to_dict(ev, org_name=org.name)
            item["is_duplicate"] = (ev.provider, ev.external_event_id) in dup_keys
            out.append(item)
        return out

    @staticmethod
    def list_refunds(
        db: Session,
        *,
        limit: int = 200,
        status: str | None = None,
        org_id: str | None = None,
        provider: str | None = None,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 200), 500))
        q = (
            select(BillingRefundReview, Organisation)
            .join(Organisation, Organisation.id == BillingRefundReview.org_id)
        )
        if status:
            norm = str(status).strip().lower()
            if norm == "processed":
                q = q.where(BillingRefundReview.review_status == "completed")
            elif norm == "under_review":
                q = q.where(BillingRefundReview.review_status.in_(("pending", "under_review", "approved")))
            else:
                q = q.where(BillingRefundReview.review_status == norm)
        if org_id:
            q = q.where(BillingRefundReview.org_id == org_id)
        if provider:
            q = q.where(BillingRefundReview.source_payment_provider == str(provider).strip().lower())
        rows = list(db.execute(q.order_by(BillingRefundReview.requested_at.desc()).limit(cap)).all())
        out: list[dict[str, Any]] = []
        for review, org in rows:
            base = SubscriptionCancellationService.refund_review_dict(review) or {}
            base["organisation_name"] = org.name
            base["org_email"] = org.contact_email
            base["billing_currency"] = resolve_org_currency(db, org)
            base["review_status_normalized"] = normalize_refund_status(review.review_status)
            out.append(base)
        return out
