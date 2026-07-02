"""Subscription cancellation, wallet credit on cancel, and admin refund review workflow."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.billing_refund_review import BillingRefundReview
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.org_audit_service import OrgAuditService
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)

CANCELLATION_NONE = "none"
CANCELLATION_REQUESTED = "requested"
CANCELLATION_SCHEDULED = "scheduled"
CANCELLATION_CANCELLED = "cancelled"
CANCELLATION_REVERSED = "reversed"

CANCEL_TYPE_PERIOD_END = "period_end"
CANCEL_TYPE_IMMEDIATE = "immediate"
CANCEL_TYPE_ADMIN_IMMEDIATE = "admin_immediate"

REFUND_TYPE_NONE = "none"
REFUND_TYPE_WALLET = "wallet_credit"
REFUND_TYPE_PAYMENT_METHOD = "payment_method_refund"
REFUND_TYPE_EITHER = "either"

REVIEW_PENDING = "pending"
REVIEW_UNDER_REVIEW = "under_review"
REVIEW_APPROVED = "approved"
REVIEW_COMPLETED = "completed"
REVIEW_PROCESSED = "processed"
REVIEW_REJECTED = "rejected"
REVIEW_FAILED = "failed"
REVIEW_CANCELLED = "cancelled"

REFUND_STATUS_ALIASES = {
    REVIEW_COMPLETED: REVIEW_PROCESSED,
    REVIEW_PROCESSED: REVIEW_COMPLETED,
}

PAYG_CODES = frozenset({"payg"})


class SubscriptionCancellationError(ValueError):
    pass


class SubscriptionCancellationService:
    @staticmethod
    def get_subscription(db: Session, org_id: str, *, service_code: str = "voxbulk") -> Subscription | None:
        return BillingAccessService.get_subscription(db, org_id, service_code=service_code)

    @staticmethod
    def _cancel_gocardless_if_needed(db: Session, sub: Subscription) -> bool:
        if str(sub.payment_provider or "").lower() != "gocardless":
            return False
        if not str(sub.external_subscription_id or "").strip():
            return False
        try:
            from app.services.gocardless_service import BillingService

            return BillingService.cancel_subscription_for_sub(db, sub)
        except Exception:
            logger.exception("gocardless_subscription_cancel_failed subscription_id=%s", sub.id)
            return False

    @staticmethod
    def _clear_card_credentials_if_needed(db: Session, sub: Subscription) -> bool:
        from app.services.card_plan_change_service import CardPlanChangeService

        return CardPlanChangeService.clear_stored_credentials(db, sub)

    @staticmethod
    def _notify_subscription_ended(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan | None,
        user_id: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        from app.services.billing_refund_email_service import BillingRefundEmailService
        from app.services.notification_service import NotificationService

        when = ended_at or datetime.utcnow()
        plan_name = getattr(plan, "name", None) if plan else None
        BillingRefundEmailService.send_subscription_ended(
            db,
            org=org,
            user_id=user_id or sub.cancellation_requested_by_user_id,
            service_code=sub.service_code,
            plan_name=plan_name,
        )
        NotificationService.notify_org_subscription_ended(
            db,
            org_id=org.id,
            subscription_id=sub.id,
            service_code=sub.service_code,
            plan_name=plan_name,
            ended_at=when,
        )

    @staticmethod
    def get_plan(db: Session, plan_id: str | None) -> Plan | None:
        if not plan_id:
            return None
        return db.get(Plan, plan_id)

    @staticmethod
    def effective_status(sub: Subscription, *, as_of: datetime | None = None) -> str:
        now = as_of or datetime.utcnow()
        base = str(sub.status or "active").strip().lower()
        cancel_status = str(sub.cancellation_status or CANCELLATION_NONE).strip().lower()
        if cancel_status == CANCELLATION_SCHEDULED and sub.cancellation_effective_at and now >= sub.cancellation_effective_at:
            return "cancelled"
        if cancel_status == CANCELLATION_CANCELLED:
            return "cancelled"
        return base

    @staticmethod
    def monthly_plan_minor(db: Session, org: Organisation, plan: Plan) -> int:
        currency = resolve_org_currency(db, org)
        row = PlanPriceService.get_price(db, plan.id, currency)
        if row and row.monthly_price_minor is not None:
            return max(0, int(row.monthly_price_minor))
        if currency == "GBP" and plan.price_gbp_pence:
            return max(0, int(plan.price_gbp_pence))
        return 0

    @staticmethod
    def calculate_unused_value_pence(
        db: Session,
        org: Organisation,
        sub: Subscription,
        plan: Plan,
        *,
        as_of: datetime | None = None,
    ) -> int:
        """Conservative proration: remaining days in current period × monthly plan price, rounded down."""
        now = as_of or datetime.utcnow()
        period_end = sub.current_period_end
        if not period_end or now >= period_end:
            return 0
        period_start = period_end - timedelta(days=30)
        if period_start > now:
            period_start = sub.created_at or period_start
        total_days = max(1, (period_end - period_start).days)
        remaining_days = max(0, (period_end - now).days)
        monthly = SubscriptionCancellationService.monthly_plan_minor(db, org, plan)
        if monthly <= 0:
            return 0
        return int(monthly * remaining_days / total_days)

    @staticmethod
    def _latest_paid_subscription_invoice(db: Session, org_id: str) -> BillingInvoice | None:
        rows = list(
            db.execute(
                select(BillingInvoice)
                .where(
                    BillingInvoice.org_id == org_id,
                    BillingInvoice.status == "paid",
                )
                .order_by(BillingInvoice.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        for row in rows:
            desc = str(row.description or "").lower()
            if "subscription" in desc or str(row.external_invoice_id or "").startswith("sub-monthly"):
                return row
        return rows[0] if rows else None

    @staticmethod
    def _assert_cancellable(sub: Subscription, plan: Plan | None) -> None:
        if plan is None:
            raise SubscriptionCancellationError("No active plan found for this subscription.")
        if str(plan.code or "").lower() in PAYG_CODES or str(sub.payment_provider or "").lower() == "payg":
            raise SubscriptionCancellationError("Pay as you go has no subscription to cancel — stop topping up your wallet instead.")
        cancel_status = str(sub.cancellation_status or CANCELLATION_NONE).lower()
        if cancel_status in {CANCELLATION_SCHEDULED, CANCELLATION_CANCELLED}:
            raise SubscriptionCancellationError("A cancellation is already scheduled or completed.")
        if str(sub.status or "").lower() == "cancelled":
            raise SubscriptionCancellationError("Subscription is already cancelled.")

    @staticmethod
    def cancellation_dict(
        db: Session,
        org: Organisation,
        sub: Subscription | None,
        plan: Plan | None,
        *,
        refund_review: BillingRefundReview | None = None,
    ) -> dict[str, Any]:
        if sub is None:
            return {"status": CANCELLATION_NONE, "can_request_cancellation": False}
        currency = resolve_org_currency(db, org)
        unused = SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan) if plan else 0
        effective = SubscriptionCancellationService.effective_status(sub)
        outstanding = BillingAccessService.outstanding_invoice_minor(db, org.id)
        return {
            "status": str(sub.cancellation_status or CANCELLATION_NONE),
            "effective_subscription_status": effective,
            "cancellation_type": sub.cancellation_type,
            "cancellation_reason": sub.cancellation_reason,
            "requested_at": sub.cancellation_requested_at.isoformat() if sub.cancellation_requested_at else None,
            "effective_at": sub.cancellation_effective_at.isoformat() if sub.cancellation_effective_at else None,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "requested_refund_type": sub.requested_refund_type,
            "calculated_unused_value_pence": unused,
            "calculated_unused_value_display": money_display(unused, currency),
            "can_request_cancellation": str(sub.cancellation_status or CANCELLATION_NONE) in {CANCELLATION_NONE, CANCELLATION_REVERSED},
            "can_reverse_cancellation": str(sub.cancellation_status or CANCELLATION_NONE).lower()
            in {CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED},
            "can_request_immediate_cancellation": False,
            "outstanding_invoice_minor": outstanding,
            "refund_review": SubscriptionCancellationService.refund_review_dict(refund_review) if refund_review else None,
            "policy_notes": {
                "period_end_default": True,
                "wallet_credit_automated": False,
                "payment_method_refund_automated": False,
                "open_invoices_block_wallet_credit": outstanding > 0,
            },
        }

    @staticmethod
    def refund_review_dict(row: BillingRefundReview | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "org_id": row.org_id,
            "subscription_id": row.subscription_id,
            "requested_refund_type": row.requested_refund_type,
            "review_status": row.review_status,
            "calculated_unused_value_pence": row.calculated_unused_value_pence,
            "approved_wallet_credit_pence": row.approved_wallet_credit_pence,
            "approved_external_refund_pence": row.approved_external_refund_pence,
            "source_payment_provider": row.source_payment_provider,
            "source_payment_reference": row.source_payment_reference,
            "admin_notes": row.admin_notes,
            "wallet_transaction_id": row.wallet_transaction_id,
            "credit_note_id": row.credit_note_id,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "support_ticket_id": row.support_ticket_id,
        }

    @staticmethod
    def get_open_refund_review(db: Session, org_id: str) -> BillingRefundReview | None:
        return (
            db.execute(
                select(BillingRefundReview)
                .where(
                    BillingRefundReview.org_id == org_id,
                    BillingRefundReview.review_status.in_(
                        (REVIEW_PENDING, REVIEW_UNDER_REVIEW, REVIEW_APPROVED)
                    ),
                )
                .order_by(BillingRefundReview.requested_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    @staticmethod
    def request_cancellation(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        cancellation_type: str = CANCEL_TYPE_PERIOD_END,
        reason: str | None = None,
        requested_refund_type: str = REFUND_TYPE_NONE,
        service_code: str = "voxbulk",
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise SubscriptionCancellationError("Organisation not found")
        sub = SubscriptionCancellationService.get_subscription(db, org_id, service_code=service_code)
        if sub is None:
            raise SubscriptionCancellationError("No subscription found")
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
        SubscriptionCancellationService._assert_cancellable(sub, plan)

        cancel_type = str(cancellation_type or CANCEL_TYPE_PERIOD_END).strip().lower()
        if cancel_type not in {CANCEL_TYPE_PERIOD_END}:
            raise SubscriptionCancellationError("Only cancel at period end is available for self-service. Contact support for immediate cancellation.")

        refund_pref = str(requested_refund_type or REFUND_TYPE_NONE).strip().lower()
        allowed_refunds = {REFUND_TYPE_NONE, REFUND_TYPE_PAYMENT_METHOD}
        if service_code == "voxbulk":
            allowed_refunds |= {REFUND_TYPE_WALLET, REFUND_TYPE_EITHER}
        if refund_pref not in allowed_refunds:
            raise SubscriptionCancellationError("Invalid refund preference")

        now = datetime.utcnow()
        effective_at = sub.current_period_end or (now + timedelta(days=30))
        sub.cancellation_status = CANCELLATION_SCHEDULED
        sub.cancellation_type = cancel_type
        sub.cancellation_reason = (reason or "").strip()[:2000] or None
        sub.cancellation_requested_at = now
        sub.cancellation_effective_at = effective_at
        sub.requested_refund_type = refund_pref if refund_pref != REFUND_TYPE_NONE else None
        sub.cancellation_requested_by_user_id = user_id
        sub.pending_plan_id = None
        sub.cancel_at_period_end = True
        sub.updated_at = now
        db.add(sub)
        from app.services.billing_finance_service import BillingFinanceService

        BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan, commit=False)

        refund_review = None
        if refund_pref in {REFUND_TYPE_PAYMENT_METHOD, REFUND_TYPE_EITHER, REFUND_TYPE_WALLET}:
            refund_review = SubscriptionCancellationService._create_refund_review(
                db,
                org=org,
                sub=sub,
                plan=plan,
                user_id=user_id,
                requested_refund_type=refund_pref,
                idempotency_key=f"cancel:{sub.id}:{now.date().isoformat()}",
            )

        OrgAuditService.record(
            db,
            org_id=org_id,
            action="Subscription cancellation requested",
            event_type="subscription.cancellation_requested",
            entity_type="subscription",
            entity_id=sub.id,
            actor_user_id=user_id,
            detail=f"Cancel at period end — effective {effective_at.date().isoformat()}",
            metadata={
                "cancellation_type": cancel_type,
                "requested_refund_type": refund_pref,
                "effective_at": effective_at.isoformat(),
            },
            commit=False,
        )
        ticket = SubscriptionCancellationService._ensure_billing_request_ticket(
            db,
            org=org,
            sub=sub,
            user_id=user_id,
            reason=reason,
            refund_review=refund_review,
            effective_at=effective_at,
            refund_pref=refund_pref,
        )
        if ticket is not None and refund_review is None and sub.cancellation_support_ticket_id is None:
            sub.cancellation_support_ticket_id = ticket.id
            db.add(sub)
        if user_id:
            from app.services.notification_service import NotificationService

            NotificationService.create_billing_request_notification(
                db,
                org_id=org_id,
                user_id=user_id,
                title="Cancellation request submitted",
                message=f"Your subscription cancellation is scheduled for {effective_at.date().isoformat()}.",
                dedupe_key=f"billing-request:cancel:{sub.id}:{now.date().isoformat()}",
            )
        from app.services.billing_refund_email_service import BillingRefundEmailService

        BillingRefundEmailService.send_cancellation_requested(
            db,
            org=org,
            user_id=user_id,
            effective_date=effective_at.date().isoformat(),
            refund_preference=refund_pref,
            estimated_refund_pence=SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan) if plan else 0,
        )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=org.contact_email or "admin@voxbulk.com",
            event_kind="subscription.cancellation_scheduled",
            source="customer" if user_id else "admin",
            actor_user_id=user_id,
            subscription_id=sub.id,
            metadata={
                "effective_at": effective_at.isoformat(),
                "requested_refund_type": refund_pref,
                "refund_review_id": refund_review.id if refund_review else None,
            },
            commit=False,
        )
        db.commit()
        db.refresh(sub)
        SubscriptionCancellationService._cancel_gocardless_if_needed(db, sub)
        if refund_review:
            db.refresh(refund_review)
        return SubscriptionCancellationService.cancellation_dict(db, org, sub, plan, refund_review=refund_review)

    @staticmethod
    def _create_refund_review(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan | None,
        user_id: str | None,
        requested_refund_type: str,
        idempotency_key: str | None = None,
    ) -> BillingRefundReview:
        existing = None
        if idempotency_key:
            existing = db.execute(
                select(BillingRefundReview).where(BillingRefundReview.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
        if existing is not None:
            return existing

        open_review = SubscriptionCancellationService.get_open_refund_review(db, org.id)
        if open_review is not None:
            return open_review

        invoice = SubscriptionCancellationService._latest_paid_subscription_invoice(db, org.id)
        unused = SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan) if plan else 0
        now = datetime.utcnow()
        row = BillingRefundReview(
            id=str(uuid.uuid4()),
            org_id=org.id,
            subscription_id=sub.id,
            source_payment_provider=(str(invoice.payment_method or invoice.provider or sub.payment_provider or "unknown")[:30] if invoice else str(sub.payment_provider or "unknown")[:30]),
            source_payment_reference=(str(invoice.payment_reference or invoice.dd_payment_id or invoice.external_invoice_id or "")[:128] if invoice else None),
            source_invoice_id=invoice.id if invoice else None,
            requested_by_user_id=user_id,
            requested_at=now,
            requested_refund_type=requested_refund_type,
            calculated_unused_value_pence=unused,
            review_status=REVIEW_PENDING,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        OrgAuditService.record(
            db,
            org_id=org.id,
            action="Refund review created",
            event_type="refund_review.created",
            entity_type="billing_refund_review",
            entity_id=row.id,
            actor_user_id=user_id,
            metadata={"requested_refund_type": requested_refund_type, "unused_value_pence": unused},
            commit=False,
        )
        return row

    @staticmethod
    def reverse_cancellation(
        db: Session,
        *,
        org_id: str,
        admin_user_id: str | None,
        note: str | None = None,
        service_code: str = "voxbulk",
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        sub = SubscriptionCancellationService.get_subscription(db, org_id, service_code=service_code)
        if org is None or sub is None:
            raise SubscriptionCancellationError("Subscription not found")
        if str(sub.cancellation_status or CANCELLATION_NONE) not in {CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED}:
            raise SubscriptionCancellationError("No scheduled cancellation to reverse")

        now = datetime.utcnow()
        sub.cancellation_status = CANCELLATION_REVERSED
        sub.cancellation_type = None
        sub.cancellation_reason = None
        sub.cancellation_requested_at = None
        sub.cancellation_effective_at = None
        sub.requested_refund_type = None
        sub.cancellation_requested_by_user_id = None
        sub.cancel_at_period_end = False
        sub.updated_at = now
        db.add(sub)
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
        from app.services.billing_finance_service import BillingFinanceService

        BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan, commit=False)

        open_review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        if open_review is not None:
            open_review.review_status = REVIEW_CANCELLED
            open_review.admin_notes = ((open_review.admin_notes or "") + f"\nCancelled with reversal: {note or ''}").strip()[:4000]
            open_review.resolved_by_user_id = admin_user_id
            open_review.resolved_at = now
            open_review.updated_at = now
            db.add(open_review)

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="subscription.cancellation_reversed",
            action="Subscription cancellation reversed",
            entity_type="subscription",
            entity_id=sub.id,
            actor_user_id=admin_user_id,
            detail=note,
            commit=False,
        )
        requesting_user = sub.cancellation_requested_by_user_id
        from app.services.billing_refund_email_service import BillingRefundEmailService

        BillingRefundEmailService.send_cancellation_reversed(
            db,
            org=org,
            user_id=requesting_user or admin_user_id,
        )
        if requesting_user:
            from app.services.notification_service import NotificationService

            NotificationService.create_billing_request_notification(
                db,
                org_id=org_id,
                user_id=requesting_user,
                title="Cancellation removed",
                message="Your subscription will continue as normal.",
                dedupe_key=f"billing-request:reversed:{sub.id}:{now.date().isoformat()}",
            )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=org.contact_email or "admin@voxbulk.com",
            event_kind="subscription.cancellation_reversed",
            actor_user_id=admin_user_id,
            subscription_id=sub.id,
            metadata={"note": note},
            commit=False,
        )
        db.commit()
        db.refresh(sub)
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
        return SubscriptionCancellationService.cancellation_dict(db, org, sub, plan)

    @staticmethod
    def admin_approve_immediate_cancel(
        db: Session,
        *,
        org_id: str,
        admin_user_id: str | None,
        issue_wallet_credit: bool = False,
        wallet_credit_pence: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        sub = SubscriptionCancellationService.get_subscription(db, org_id)
        if org is None or sub is None:
            raise SubscriptionCancellationError("Subscription not found")
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
        SubscriptionCancellationService._assert_cancellable(sub, plan)

        outstanding = BillingAccessService.outstanding_invoice_minor(db, org_id)
        if issue_wallet_credit and outstanding > 0:
            raise SubscriptionCancellationError("Resolve open invoices before issuing wallet credit.")

        now = datetime.utcnow()
        sub.cancellation_status = CANCELLATION_CANCELLED
        sub.cancellation_type = CANCEL_TYPE_ADMIN_IMMEDIATE
        sub.cancellation_requested_at = sub.cancellation_requested_at or now
        sub.cancellation_effective_at = now
        sub.cancellation_reason = (note or sub.cancellation_reason or "Admin immediate cancellation")[:2000]
        sub.status = "cancelled"
        sub.cancelled_at = now
        sub.pending_plan_id = None
        sub.updated_at = now
        db.add(sub)

        wallet_result = None
        if issue_wallet_credit:
            open_review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
            amount = wallet_credit_pence
            if amount is None and open_review is not None:
                amount = open_review.calculated_unused_value_pence
            if amount is None:
                amount = SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan)
            amount = int(amount or 0)
            if amount <= 0 and wallet_credit_pence is None:
                raise SubscriptionCancellationError(
                    "No unused value to credit; pass wallet_credit_pence explicitly."
                )
            wallet_result = SubscriptionCancellationService.issue_wallet_credit(
                db,
                org=org,
                sub=sub,
                amount_minor=amount,
                admin_user_id=admin_user_id,
                note=note or "Subscription cancellation wallet credit",
                refund_review=open_review,
            )
            from app.services.wallet_service import WalletService

            wallet_result = {
                **(wallet_result or {}),
                "wallet_balance_pence": WalletService.balance_minor(org),
                "wallet_balance_display": money_display(WalletService.balance_minor(org), resolve_org_currency(db, org)),
            }

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="subscription.cancellation_approved",
            action="Subscription cancelled immediately (admin)",
            entity_type="subscription",
            entity_id=sub.id,
            actor_user_id=admin_user_id,
            detail=note,
            metadata={"wallet_credit": wallet_result},
            commit=False,
        )
        requesting_user = sub.cancellation_requested_by_user_id
        if wallet_result and org:
            from app.services.billing_refund_email_service import BillingRefundEmailService

            BillingRefundEmailService.send_wallet_credit_issued(
                db,
                org=org,
                user_id=requesting_user,
                amount_pence=int(wallet_result.get("wallet_credit_pence") or 0),
                wallet_balance_pence=int(wallet_result.get("wallet_balance_pence") or 0),
            )
            if requesting_user:
                from app.services.notification_service import NotificationService

                NotificationService.create_billing_request_resolved_notification(
                    db,
                    org_id=org_id,
                    user_id=requesting_user,
                    review_status=REVIEW_APPROVED,
                    wallet_credit_pence=int(wallet_result.get("wallet_credit_pence") or 0),
                    external_refund_pence=0,
                    dedupe_key=f"billing-request:immediate-wallet:{sub.id}:{now.date().isoformat()}",
                )
        if org:
            SubscriptionCancellationService._notify_subscription_ended(
                db,
                org=org,
                sub=sub,
                plan=plan,
                user_id=requesting_user,
                ended_at=now,
            )
        SubscriptionCancellationService._cancel_gocardless_if_needed(db, sub)
        SubscriptionCancellationService._clear_card_credentials_if_needed(db, sub)
        db.commit()
        db.refresh(sub)
        open_review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        return {
            **SubscriptionCancellationService.cancellation_dict(db, org, sub, plan, refund_review=open_review),
            "wallet_credit": wallet_result,
        }

    @staticmethod
    def finalize_due_scheduled_cancellations(db: Session, *, as_of: datetime | None = None) -> dict[str, int]:
        now = as_of or datetime.utcnow()
        stats = {"finalized": 0, "wallet_credit_issued": 0, "wallet_credit_failed": 0}
        rows = list(
            db.execute(
                select(Subscription).where(
                    Subscription.cancellation_status == CANCELLATION_SCHEDULED,
                    Subscription.cancellation_effective_at.is_not(None),
                    Subscription.cancellation_effective_at <= now,
                )
            )
            .scalars()
            .all()
        )
        for sub in rows:
            org = db.get(Organisation, sub.org_id)
            plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
            wallet_result = None
            review = SubscriptionCancellationService.get_open_refund_review(db, sub.org_id) if org else None
            refund_type = str(sub.requested_refund_type or "").lower()
            should_auto_wallet = (
                str(sub.service_code or "voxbulk") == "voxbulk"
                and refund_type in {REFUND_TYPE_WALLET, REFUND_TYPE_EITHER}
            )
            SubscriptionCancellationService._cancel_gocardless_if_needed(db, sub)
            SubscriptionCancellationService._clear_card_credentials_if_needed(db, sub)
            if org and plan and should_auto_wallet:
                outstanding = BillingAccessService.outstanding_invoice_minor(db, org.id)
                if outstanding > 0:
                    stats["wallet_credit_failed"] += 1
                    from app.services.payment_event_service import PaymentEventService

                    PaymentEventService.record_finance(
                        db,
                        org_id=org.id,
                        client_email=org.contact_email or "admin@voxbulk.com",
                        status="failed",
                        event_kind="wallet.cancellation_credit_failed",
                        source="system",
                        subscription_id=sub.id,
                        failure_reason="Outstanding invoices block wallet credit at period end",
                        metadata={"outstanding_invoice_minor": outstanding},
                        commit=False,
                    )
                    OrgAuditService.record(
                        db,
                        org_id=org.id,
                        action="Period-end wallet credit blocked",
                        event_type="subscription.cancellation_wallet_blocked",
                        entity_type="subscription",
                        entity_id=sub.id,
                        metadata={"outstanding_invoice_minor": outstanding},
                        commit=False,
                    )
                else:
                    unused = SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan)
                    if unused > 0:
                        try:
                            wallet_result = SubscriptionCancellationService.issue_wallet_credit(
                                db,
                                org=org,
                                sub=sub,
                                amount_minor=unused,
                                admin_user_id=None,
                                note="Unused subscription value at period end",
                                refund_review=review,
                            )
                            stats["wallet_credit_issued"] += 1
                            if review and wallet_result.get("wallet_transaction_id"):
                                review.review_status = REVIEW_COMPLETED
                                review.resolved_at = now
                                review.updated_at = now
                                db.add(review)
                        except SubscriptionCancellationError as exc:
                            stats["wallet_credit_failed"] += 1
                            wallet_result = {"error": str(exc)}
                            from app.services.payment_event_service import PaymentEventService

                            PaymentEventService.record_finance(
                                db,
                                org_id=org.id,
                                client_email=org.contact_email or "admin@voxbulk.com",
                                status="failed",
                                event_kind="wallet.cancellation_credit_failed",
                                source="system",
                                subscription_id=sub.id,
                                failure_reason=str(exc)[:500],
                                metadata={"unused_minor": unused},
                                commit=False,
                            )
                            OrgAuditService.record(
                                db,
                                org_id=org.id,
                                action="Period-end wallet credit failed",
                                event_type="subscription.cancellation_wallet_failed",
                                entity_type="subscription",
                                entity_id=sub.id,
                                metadata={"error": str(exc), "unused_minor": unused},
                                commit=False,
                            )

            sub.cancellation_status = CANCELLATION_CANCELLED
            sub.status = "cancelled"
            sub.cancelled_at = now
            sub.cancel_at_period_end = False
            sub.next_billing_date = None
            sub.updated_at = now
            db.add(sub)
            if org:
                from app.services.billing_finance_service import BillingFinanceService

                BillingFinanceService.sync_subscription_billing_fields(
                    db, sub, org=org, plan=plan, commit=False
                )
            OrgAuditService.record(
                db,
                org_id=sub.org_id,
                action="Subscription cancellation effective",
                event_type="subscription.cancellation_effective",
                entity_type="subscription",
                entity_id=sub.id,
                metadata={"effective_at": now.isoformat(), "wallet_result": wallet_result},
                commit=False,
            )
            if org:
                from app.services.payment_event_service import PaymentEventService

                PaymentEventService.record_finance(
                    db,
                    org_id=org.id,
                    client_email=org.contact_email or "admin@voxbulk.com",
                    event_kind="subscription.cancellation_closed",
                    source="system",
                    subscription_id=sub.id,
                    metadata={
                        "wallet_result": wallet_result,
                        "requested_refund_type": refund_type,
                    },
                    commit=False,
                )
                SubscriptionCancellationService._notify_subscription_ended(
                    db,
                    org=org,
                    sub=sub,
                    plan=plan,
                    user_id=sub.cancellation_requested_by_user_id,
                    ended_at=now,
                )
            stats["finalized"] += 1
        if stats["finalized"]:
            db.commit()
        return stats

    @staticmethod
    def issue_wallet_credit(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        amount_minor: int,
        admin_user_id: str | None,
        note: str | None,
        refund_review: BillingRefundReview | None,
    ) -> dict[str, Any]:
        amount = max(0, int(amount_minor or 0))
        if amount <= 0:
            return {"wallet_credit_pence": 0}

        review = refund_review or SubscriptionCancellationService.get_open_refund_review(db, org.id)
        if review and review.wallet_transaction_id:
            raise SubscriptionCancellationError("Wallet credit already issued for this refund review.")

        from app.services.billing_settings_service import BillingSettingsService
        from app.services.wallet_service import WalletService

        currency = resolve_org_currency(db, org)
        cn_number = BillingSettingsService.allocate_credit_note_number(db)
        from app.models.credit_note import CreditNote

        credit_note = CreditNote(
            id=str(uuid.uuid4()),
            org_id=org.id,
            invoice_id=review.source_invoice_id if review else None,
            credit_note_number=cn_number,
            amount_minor=amount,
            currency=currency,
            reason=(note or "Subscription cancellation wallet credit")[:512],
            status="issued",
            refund_method="wallet",
            created_by_user_id=admin_user_id,
            created_at=datetime.utcnow(),
        )
        db.add(credit_note)
        db.flush()

        tx = WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="subscription_cancellation_credit",
            description=f"Subscription cancellation credit — {cn_number}"[:500],
            invoice_id=review.source_invoice_id if review else None,
            created_by_user_id=admin_user_id,
            metadata={
                "credit_note_id": credit_note.id,
                "subscription_id": sub.id,
                "refund_review_id": review.id if review else None,
            },
            commit=False,
        )

        if review:
            review.approved_wallet_credit_pence = amount
            review.wallet_transaction_id = tx.id
            review.credit_note_id = credit_note.id
            if review.review_status == REVIEW_PENDING:
                review.review_status = REVIEW_APPROVED
            review.updated_at = datetime.utcnow()
            db.add(review)

        OrgAuditService.record_admin(
            db,
            org_id=org.id,
            event_type="wallet.cancellation_credit",
            action="Wallet credit issued for cancellation",
            entity_type="wallet_transaction",
            entity_id=tx.id,
            actor_user_id=admin_user_id,
            metadata={"amount_minor": amount, "credit_note_id": credit_note.id},
            commit=False,
        )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org.id,
            client_email=org.contact_email or "admin@voxbulk.com",
            event_kind="wallet.cancellation_credit",
            actor_user_id=admin_user_id,
            subscription_id=sub.id,
            metadata={
                "amount_minor": amount,
                "wallet_transaction_id": tx.id,
                "credit_note_id": credit_note.id,
                "refund_review_id": review.id if review else None,
            },
            commit=False,
        )
        db.flush()
        return {
            "wallet_credit_pence": amount,
            "wallet_transaction_id": tx.id,
            "credit_note_id": credit_note.id,
            "credit_note_number": cn_number,
        }

    @staticmethod
    def resolve_refund_review(
        db: Session,
        *,
        review_id: str,
        admin_user_id: str | None,
        review_status: str,
        admin_notes: str | None = None,
        approved_external_refund_pence: int | None = None,
        issue_wallet_credit: bool = False,
        wallet_credit_pence: int | None = None,
    ) -> dict[str, Any]:
        review = db.get(BillingRefundReview, review_id)
        if review is None:
            raise SubscriptionCancellationError("Refund review not found")
        if review.review_status in {REVIEW_COMPLETED, REVIEW_PROCESSED, REVIEW_REJECTED, REVIEW_CANCELLED, REVIEW_FAILED}:
            raise SubscriptionCancellationError("Refund review is already resolved")

        org = db.get(Organisation, review.org_id)
        sub = db.get(Subscription, review.subscription_id) if review.subscription_id else None
        plan = SubscriptionCancellationService.get_plan(db, sub.plan_id) if sub else None
        now = datetime.utcnow()

        wallet_result = None
        if issue_wallet_credit and review.wallet_transaction_id:
            raise SubscriptionCancellationError("Wallet credit already issued for this refund review.")
        if issue_wallet_credit and sub and org:
            outstanding = BillingAccessService.outstanding_invoice_minor(db, org.id)
            if outstanding > 0:
                raise SubscriptionCancellationError("Resolve open invoices before issuing wallet credit.")
            amount = wallet_credit_pence if wallet_credit_pence is not None else review.calculated_unused_value_pence
            amount = int(amount or 0)
            if amount <= 0 and wallet_credit_pence is None:
                amount = int(SubscriptionCancellationService.calculate_unused_value_pence(db, org, sub, plan) or 0)
            if amount <= 0 and wallet_credit_pence is None:
                raise SubscriptionCancellationError(
                    "No unused value to credit; pass wallet_credit_pence explicitly."
                )
            wallet_result = SubscriptionCancellationService.issue_wallet_credit(
                db,
                org=org,
                sub=sub,
                amount_minor=amount,
                admin_user_id=admin_user_id,
                note=admin_notes,
                refund_review=review,
            )
            from app.services.wallet_service import WalletService

            wallet_result = {
                **(wallet_result or {}),
                "wallet_balance_pence": WalletService.balance_minor(org),
                "wallet_balance_display": money_display(WalletService.balance_minor(org), resolve_org_currency(db, org)),
            }

        status = str(review_status or REVIEW_COMPLETED).strip().lower()
        if status == REVIEW_PROCESSED:
            status = REVIEW_COMPLETED
        allowed = {REVIEW_UNDER_REVIEW, REVIEW_APPROVED, REVIEW_COMPLETED, REVIEW_REJECTED, REVIEW_FAILED}
        if status not in allowed:
            raise SubscriptionCancellationError("Invalid review status")

        if approved_external_refund_pence is not None:
            ext = max(0, int(approved_external_refund_pence))
            already_wallet = int(review.approved_wallet_credit_pence or 0)
            calculated = int(review.calculated_unused_value_pence or 0)
            if calculated and ext + already_wallet > calculated:
                raise SubscriptionCancellationError("External refund plus wallet credit cannot exceed calculated unused value.")
            provider = str(review.source_payment_provider or "").lower()
            payment_ref = str(review.source_payment_reference or "").strip()
            stripe_refund_id = None
            if ext > 0 and provider == "stripe" and payment_ref.startswith("pi_"):
                from app.services.stripe_payment_service import StripePaymentService, StripeProviderError

                try:
                    stripe_result = StripePaymentService.issue_refund(
                        db,
                        payment_intent_id=payment_ref,
                        amount_minor=ext,
                    )
                    stripe_refund_id = stripe_result.get("refund_id")
                    note_suffix = f"Stripe refund {stripe_refund_id}"
                    review.admin_notes = ((review.admin_notes or "") + f"\n{note_suffix}").strip()[:4000]
                except StripeProviderError as exc:
                    review.review_status = REVIEW_FAILED
                    review.admin_notes = ((review.admin_notes or "") + f"\nStripe refund failed: {exc}").strip()[:4000]
                    review.resolved_by_user_id = admin_user_id
                    review.resolved_at = now
                    review.updated_at = now
                    db.add(review)
                    from app.services.payment_event_service import PaymentEventService

                    PaymentEventService.record(
                        db,
                        org_id=review.org_id,
                        client_email=org.contact_email if org else "admin@voxbulk.com",
                        status="failed",
                        event_kind="refund.failed",
                        source="stripe",
                        failure_reason=str(exc)[:500],
                        actor_user_id=admin_user_id,
                        subscription_id=review.subscription_id,
                        metadata={"refund_review_id": review.id},
                        commit=False,
                    )
                    OrgAuditService.record_admin(
                        db,
                        org_id=review.org_id,
                        event_type="refund_review.failed",
                        action="Refund review failed",
                        entity_type="billing_refund_review",
                        entity_id=review.id,
                        actor_user_id=admin_user_id,
                        detail=str(exc)[:500],
                        commit=False,
                    )
                    db.commit()
                    db.refresh(review)
                    raise SubscriptionCancellationError(f"Stripe refund failed: {exc}") from exc
            review.approved_external_refund_pence = ext

        review.review_status = status
        review.admin_notes = (admin_notes or review.admin_notes or "")[:4000] or None
        review.resolved_by_user_id = admin_user_id
        review.resolved_at = now
        review.updated_at = now
        db.add(review)

        OrgAuditService.record_admin(
            db,
            org_id=review.org_id,
            event_type=f"refund_review.{status}",
            action=f"Refund review {status}",
            entity_type="billing_refund_review",
            entity_id=review.id,
            actor_user_id=admin_user_id,
            detail=admin_notes,
            metadata={"wallet_result": wallet_result, "approved_external_refund_pence": review.approved_external_refund_pence},
            commit=False,
        )
        from app.services.payment_event_service import PaymentEventService

        event_status = "failed" if status == REVIEW_FAILED else "succeeded"
        PaymentEventService.record_finance(
            db,
            org_id=review.org_id,
            client_email=(org.contact_email if org else None) or "admin@voxbulk.com",
            status=event_status,
            event_kind=f"refund.{status}",
            actor_user_id=admin_user_id,
            subscription_id=review.subscription_id,
            metadata={
                "refund_review_id": review.id,
                "wallet_result": wallet_result,
                "approved_external_refund_pence": review.approved_external_refund_pence,
            },
            commit=False,
        )
        db.commit()
        db.refresh(review)
        requesting_user = review.requested_by_user_id
        if org and requesting_user and status in {REVIEW_APPROVED, REVIEW_COMPLETED, REVIEW_REJECTED}:
            from app.services.billing_refund_email_service import BillingRefundEmailService
            from app.services.notification_service import NotificationService

            wallet_pence = int(review.approved_wallet_credit_pence or 0)
            external_pence = int(review.approved_external_refund_pence or 0)
            if wallet_pence > 0 and wallet_result:
                from app.services.wallet_service import WalletService

                BillingRefundEmailService.send_wallet_credit_issued(
                    db,
                    org=org,
                    user_id=requesting_user,
                    amount_pence=wallet_pence,
                    wallet_balance_pence=WalletService.balance_minor(org),
                )
            if external_pence > 0 and status in {REVIEW_APPROVED, REVIEW_COMPLETED}:
                BillingRefundEmailService.send_bank_refund_approved(
                    db,
                    org=org,
                    user_id=requesting_user,
                    amount_pence=external_pence,
                    payment_method=str(review.source_payment_provider or "bank"),
                    payment_reference=review.source_payment_reference,
                )
            if status == REVIEW_REJECTED:
                BillingRefundEmailService.send_refund_rejected(
                    db,
                    org=org,
                    user_id=requesting_user,
                    amount_pence=int(review.calculated_unused_value_pence or 0),
                    admin_notes=review.admin_notes,
                )
            NotificationService.create_billing_request_resolved_notification(
                db,
                org_id=review.org_id,
                user_id=requesting_user,
                review_status=status,
                wallet_credit_pence=wallet_pence,
                external_refund_pence=external_pence,
                dedupe_key=f"billing-request:resolved:{review.id}:{status}",
            )
            db.commit()
        return {
            "refund_review": SubscriptionCancellationService.refund_review_dict(review),
            "wallet_credit": wallet_result,
        }

    @staticmethod
    def reverse_wallet_credit(
        db: Session,
        *,
        review_id: str,
        admin_user_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        review = db.get(BillingRefundReview, review_id)
        if review is None or not review.wallet_transaction_id:
            raise SubscriptionCancellationError("No wallet credit to reverse on this review")
        from app.models.wallet_transaction import WalletTransaction
        from app.services.wallet_service import WalletService

        tx = db.get(WalletTransaction, review.wallet_transaction_id)
        org = db.get(Organisation, review.org_id)
        if tx is None or org is None:
            raise SubscriptionCancellationError("Wallet transaction not found")
        amount = int(tx.amount_minor or 0)
        reversed_tx = WalletService.debit(
            db,
            org,
            amount_minor=amount,
            kind="refund_adjustment_reversal",
            description=f"Reversal of cancellation wallet credit {tx.id[:8]}"[:500],
            created_by_user_id=admin_user_id,
            metadata={"reversed_transaction_id": tx.id, "refund_review_id": review.id},
            commit=False,
        )
        review.approved_wallet_credit_pence = 0
        review.wallet_transaction_id = None
        review.updated_at = datetime.utcnow()
        db.add(review)
        OrgAuditService.record_admin(
            db,
            org_id=review.org_id,
            event_type="wallet.cancellation_credit_reversed",
            action="Cancellation wallet credit reversed",
            entity_type="wallet_transaction",
            entity_id=reversed_tx.id,
            actor_user_id=admin_user_id,
            detail=reason,
            commit=False,
        )
        db.commit()
        return {"reversed_transaction_id": reversed_tx.id, "refund_review": SubscriptionCancellationService.refund_review_dict(review)}

    @staticmethod
    def list_refund_reviews(
        db: Session,
        *,
        org_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        q = select(BillingRefundReview).order_by(BillingRefundReview.requested_at.desc()).limit(limit)
        if org_id:
            q = q.where(BillingRefundReview.org_id == org_id)
        if status:
            q = q.where(BillingRefundReview.review_status == status)
        rows = list(db.execute(q).scalars().all())
        return [SubscriptionCancellationService.refund_review_dict(r) for r in rows]

    @staticmethod
    def list_scheduled_cancellations(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(Subscription)
                .where(Subscription.cancellation_status.in_((CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED)))
                .order_by(Subscription.cancellation_effective_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        out = []
        for sub in rows:
            org = db.get(Organisation, sub.org_id)
            plan = SubscriptionCancellationService.get_plan(db, sub.plan_id)
            out.append(
                {
                    "org_id": sub.org_id,
                    "org_name": org.name if org else None,
                    **SubscriptionCancellationService.cancellation_dict(db, org, sub, plan),
                }
            )
        return out

    @staticmethod
    def _ensure_billing_request_ticket(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        user_id: str | None,
        reason: str | None,
        refund_review: BillingRefundReview | None,
        effective_at: datetime,
        refund_pref: str,
    ):
        if not user_id:
            return None
        if refund_review and refund_review.support_ticket_id:
            from app.models.support_ticket import SupportTicket

            return db.get(SupportTicket, refund_review.support_ticket_id)
        if sub.cancellation_support_ticket_id:
            from app.models.support_ticket import SupportTicket

            return db.get(SupportTicket, sub.cancellation_support_ticket_id)

        from app.models.support_ticket import SupportTicket
        from app.services.support_ticket_service import SupportTicketService

        existing = db.execute(
            select(SupportTicket).where(
                SupportTicket.organisation_id == org.id,
                SupportTicket.category == "invoices",
                SupportTicket.subject.like("Billing request — subscription cancellation%"),
                SupportTicket.status != "closed",
            ).order_by(SupportTicket.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            if refund_review and not refund_review.support_ticket_id:
                refund_review.support_ticket_id = existing.id
                db.add(refund_review)
            return existing

        unused = SubscriptionCancellationService.calculate_unused_value_pence(
            db, org, sub, SubscriptionCancellationService.get_plan(db, sub.plan_id)
        )
        body_lines = [
            f"Organisation: {org.name}",
            f"Effective date: {effective_at.date().isoformat()}",
            f"Refund preference: {refund_pref}",
            f"Estimated unused value: {money_display(unused, resolve_org_currency(db, org))}",
        ]
        if reason:
            body_lines.append(f"Reason: {reason.strip()}")
        ticket = SupportTicketService.create_ticket(
            db,
            org_id=org.id,
            user_id=user_id,
            category="invoices",
            subject="Billing request — subscription cancellation",
            message="\n".join(body_lines),
        )
        db.flush()
        if refund_review:
            refund_review.support_ticket_id = ticket.id
            db.add(refund_review)
        return ticket

    @staticmethod
    def _request_status_label(cancellation_status: str, review_status: str | None) -> str:
        cs = str(cancellation_status or CANCELLATION_NONE).lower()
        rs = str(review_status or "").lower()
        if rs == REVIEW_PENDING or cs in {CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED}:
            return "pending"
        if rs in {REVIEW_APPROVED, REVIEW_COMPLETED} or cs == CANCELLATION_CANCELLED:
            return "approved"
        if rs == REVIEW_REJECTED:
            return "rejected"
        if rs == REVIEW_CANCELLED:
            return "cancelled"
        return "pending"

    @staticmethod
    def list_billing_requests(
        db: Session,
        *,
        org_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        review_q = select(BillingRefundReview).order_by(BillingRefundReview.requested_at.desc()).limit(limit)
        if org_id:
            review_q = review_q.where(BillingRefundReview.org_id == org_id)
        for review in db.execute(review_q).scalars().all():
            org = db.get(Organisation, review.org_id)
            sub = db.get(Subscription, review.subscription_id) if review.subscription_id else None
            st = SubscriptionCancellationService._request_status_label(
                str(sub.cancellation_status if sub else CANCELLATION_NONE),
                review.review_status,
            )
            if status and st != status.strip().lower():
                continue
            items.append(
                {
                    "id": review.id,
                    "type": "refund_review",
                    "org_id": review.org_id,
                    "org_name": org.name if org else None,
                    "status": st,
                    "review_status": review.review_status,
                    "requested_refund_type": review.requested_refund_type,
                    "calculated_unused_value_pence": review.calculated_unused_value_pence,
                    "approved_wallet_credit_pence": review.approved_wallet_credit_pence,
                    "admin_notes": review.admin_notes,
                    "support_ticket_id": review.support_ticket_id,
                    "requested_at": review.requested_at.isoformat() if review.requested_at else None,
                    "resolved_at": review.resolved_at.isoformat() if review.resolved_at else None,
                }
            )

        sub_q = (
            select(Subscription)
            .where(Subscription.cancellation_status.in_((CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED, CANCELLATION_CANCELLED)))
            .order_by(Subscription.cancellation_requested_at.desc())
            .limit(limit)
        )
        if org_id:
            sub_q = sub_q.where(Subscription.org_id == org_id)
        seen_orgs_with_review = {i["org_id"] for i in items if i["type"] == "refund_review"}
        for sub in db.execute(sub_q).scalars().all():
            if sub.org_id in seen_orgs_with_review and str(sub.cancellation_status or "").lower() != CANCELLATION_CANCELLED:
                continue
            org = db.get(Organisation, sub.org_id)
            st = SubscriptionCancellationService._request_status_label(str(sub.cancellation_status), None)
            if status and st != status.strip().lower():
                continue
            items.append(
                {
                    "id": sub.id,
                    "type": "cancellation",
                    "org_id": sub.org_id,
                    "org_name": org.name if org else None,
                    "status": st,
                    "cancellation_status": sub.cancellation_status,
                    "requested_refund_type": sub.requested_refund_type,
                    "effective_at": sub.cancellation_effective_at.isoformat() if sub.cancellation_effective_at else None,
                    "support_ticket_id": sub.cancellation_support_ticket_id,
                    "requested_at": sub.cancellation_requested_at.isoformat() if sub.cancellation_requested_at else None,
                    "resolved_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
                }
            )
        items.sort(key=lambda x: str(x.get("requested_at") or ""), reverse=True)
        return items[:limit]
