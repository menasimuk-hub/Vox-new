"""Launch access control — credit limits, mandate status, first-payment rules."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.subscription import Subscription
from app.services.billing_currency import money_display, resolve_org_currency

logger = logging.getLogger(__name__)

OUTSTANDING_STATUSES = frozenset(
    {
        "pending",
        "failed",
        "past_due",
        "collecting",
        "issued",
        "disputed",
        "open",
        "due",
        "unpaid",
        "overdue",
        "sent",
    }
)
IMMEDIATE_ACCESS_SCHEMES = frozenset({"bacs", "sepa_core", "sepa_cor1"})
DEFERRED_FIRST_PAYMENT_SCHEMES = frozenset({"ach", "pad", "becs", "becs_nz", "autogiro", "betalingsservice"})
FIRST_PAYMENT_GRACE_DAYS = 7


class BillingAccessService:
    @staticmethod
    def outstanding_invoice_minor(db: Session, org_id: str) -> int:
        rows = list(
            db.execute(
                select(BillingInvoice).where(
                    BillingInvoice.org_id == org_id,
                    BillingInvoice.status.in_(tuple(OUTSTANDING_STATUSES)),
                )
            )
            .scalars()
            .all()
        )
        total = 0
        for row in rows:
            total += int(row.subtotal_pence if row.subtotal_pence is not None else row.amount_gbp_pence or 0)
        return max(0, total)

    @staticmethod
    def effective_credit_limit_minor(db: Session, org: Organisation) -> int:
        limit = int(getattr(org, "credit_limit_minor", 0) or 0)
        return max(0, limit)

    @staticmethod
    def credit_limit_exceeded(db: Session, org: Organisation) -> tuple[bool, dict[str, Any]]:
        limit = BillingAccessService.effective_credit_limit_minor(db, org)
        if limit <= 0:
            return False, {"credit_limit_minor": 0, "outstanding_minor": 0}
        outstanding = BillingAccessService.outstanding_invoice_minor(db, org.id)
        currency = resolve_org_currency(db, org)
        exceeded = outstanding > limit
        return exceeded, {
            "credit_limit_minor": limit,
            "credit_limit_display": money_display(limit, currency),
            "outstanding_minor": outstanding,
            "outstanding_display": money_display(outstanding, currency),
            "currency": currency,
        }

    @staticmethod
    def get_subscription(db: Session, org_id: str, *, service_code: str = "voxbulk") -> Subscription | None:
        return (
            db.execute(
                select(Subscription)
                .where(
                    Subscription.org_id == org_id,
                    Subscription.service_code == service_code,
                )
                .order_by(Subscription.updated_at.desc(), Subscription.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    @staticmethod
    def get_feedback_subscription(db: Session, org_id: str) -> Subscription | None:
        return BillingAccessService.get_subscription(db, org_id, service_code="customer_feedback")

    @staticmethod
    def mandate_blocks_launch(db: Session, org_id: str) -> str | None:
        sub = BillingAccessService.get_subscription(db, org_id)
        if sub is None:
            return None
        mandate_status = str(sub.mandate_status or "").strip().lower()
        if mandate_status in {"cancelled", "failed", "expired"}:
            return "Your Direct Debit mandate is no longer active. Update your payment details in Account → Packages."
        if str(sub.status or "").strip().lower() == "suspended":
            return "Your account is suspended due to a failed first payment. Contact support or update your mandate."
        return None

    @staticmethod
    def pending_first_payment_blocks_dd(db: Session, org_id: str) -> bool:
        sub = BillingAccessService.get_subscription(db, org_id)
        if sub is None:
            return False
        return str(sub.status or "").strip().lower() == "pending_first_payment"

    @staticmethod
    def launch_block_reason(db: Session, org: Organisation) -> str | None:
        exceeded, detail = BillingAccessService.credit_limit_exceeded(db, org)
        if exceeded:
            return (
                f"Outstanding invoices ({detail['outstanding_display']}) exceed your credit limit "
                f"({detail['credit_limit_display']}). Pay or resolve open invoices before launching."
            )
        mandate_block = BillingAccessService.mandate_blocks_launch(db, org.id)
        if mandate_block:
            return mandate_block
        sub = BillingAccessService.get_subscription(db, org.id)
        if sub is not None:
            from app.services.subscription_cancellation_service import (
                CANCELLATION_CANCELLED,
                SubscriptionCancellationService,
            )

            cancel_status = str(sub.cancellation_status or "none").strip().lower()
            if cancel_status == CANCELLATION_CANCELLED or SubscriptionCancellationService.effective_status(sub) == "cancelled":
                return "Your subscription has ended. Choose a plan on Packages & pricing to launch new campaigns."
            if str(sub.status or "").strip().lower() == "past_due":
                return "Your account has a past-due invoice. Resolve billing before launching new campaigns."
        return None

    @staticmethod
    def access_summary(db: Session, org: Organisation) -> dict[str, Any]:
        sub = BillingAccessService.get_subscription(db, org.id)
        exceeded, credit = BillingAccessService.credit_limit_exceeded(db, org)
        block = BillingAccessService.launch_block_reason(db, org)
        return {
            "can_launch": block is None,
            "launch_block_reason": block,
            "credit_limit_exceeded": exceeded,
            **credit,
            "mandate_status": getattr(sub, "mandate_status", None) if sub else None,
            "subscription_status": sub.status if sub else None,
            "pending_first_payment": BillingAccessService.pending_first_payment_blocks_dd(db, org.id),
            "allow_overage": bool(getattr(org, "allow_overage", True)),
        }

    @staticmethod
    def classify_mandate_scheme(scheme: str | None) -> str:
        clean = str(scheme or "").strip().lower()
        if clean in IMMEDIATE_ACCESS_SCHEMES or clean.startswith("bacs"):
            return "immediate"
        if clean in DEFERRED_FIRST_PAYMENT_SCHEMES:
            return "deferred_first_payment"
        return "immediate"

    @staticmethod
    def apply_mandate_setup_access(
        db: Session,
        *,
        sub: Subscription,
        mandate_id: str,
        scheme: str | None = None,
    ) -> Subscription:
        now = datetime.utcnow()
        sub.mandate_id = str(mandate_id or "").strip() or sub.mandate_id
        sub.mandate_status = "active"
        mode = BillingAccessService.classify_mandate_scheme(scheme)
        if mode == "deferred_first_payment":
            sub.status = "pending_first_payment"
        elif str(sub.status or "").strip().lower() in {"", "pending_payment"}:
            sub.status = "active"
        sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def mark_first_payment_confirmed(db: Session, *, org_id: str, sub: Subscription | None = None) -> None:
        sub = sub or BillingAccessService.get_subscription(db, org_id)
        if sub is None:
            return
        now = datetime.utcnow()
        if sub.first_payment_at is None:
            sub.first_payment_at = now
        if str(sub.status or "").strip().lower() == "pending_first_payment":
            sub.status = "active"
        sub.updated_at = now
        db.add(sub)
        db.commit()

    @staticmethod
    def handle_first_payment_failure(db: Session, *, org_id: str) -> bool:
        """Suspend org when first DD fails within the grace window."""
        sub = BillingAccessService.get_subscription(db, org_id)
        if sub is None:
            return False
        if str(sub.status or "").strip().lower() not in {"pending_first_payment", "active"}:
            return False
        anchor = sub.first_payment_at or sub.created_at or datetime.utcnow()
        if (datetime.utcnow() - anchor).days > FIRST_PAYMENT_GRACE_DAYS:
            return False
        sub.status = "suspended"
        sub.mandate_status = sub.mandate_status or "failed"
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        logger.warning("billing_first_payment_suspend org_id=%s subscription_id=%s", org_id, sub.id)
        return True

    @staticmethod
    def handle_mandate_cancelled(db: Session, *, org_id: str, mandate_id: str | None = None) -> dict[str, Any]:
        mid = str(mandate_id or "").strip()
        sub = None
        if mid:
            sub = db.execute(
                select(Subscription).where(Subscription.mandate_id == mid).limit(1)
            ).scalar_one_or_none()
        if sub is None:
            sub = BillingAccessService.get_subscription(db, org_id)
        if sub is None:
            return {"updated": False}
        if mid and sub.mandate_id and sub.mandate_id != mid:
            return {"updated": False, "reason": "mandate_mismatch"}
        now = datetime.utcnow()
        sub.mandate_status = "cancelled"
        sub.status = "past_due" if str(sub.status or "").lower() == "active" else sub.status
        sub.cancelled_at = now
        sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)

        from app.services.usage_wallet_service import UsageWalletService

        email = UsageWalletService.get_org_billing_email(db, org_id)
        if email:
            try:
                from app.services.product_email_triggers import ProductEmailTriggers

                ProductEmailTriggers.notify_general(
                    db,
                    to_email=email,
                    extra_variables={
                        "message": "Your Direct Debit mandate was cancelled. Campaign launches are blocked until you set up a new mandate in Account → Packages.",
                    },
                )
            except Exception:
                logger.exception("mandate_cancel_customer_email_failed org_id=%s", org_id)

        try:
            from app.core.config import get_settings

            admin_email = get_settings().invoice_company_email
            if admin_email:
                from app.services.product_email_triggers import ProductEmailTriggers

                ProductEmailTriggers.notify_general(
                    db,
                    to_email=str(admin_email).strip().lower(),
                    extra_variables={"message": f"Mandate cancelled for org {org_id}. Launches blocked until mandate restored."},
                )
        except Exception:
            logger.exception("mandate_cancel_admin_email_failed org_id=%s", org_id)

        return {"updated": True, "subscription_id": sub.id, "mandate_status": sub.mandate_status}
