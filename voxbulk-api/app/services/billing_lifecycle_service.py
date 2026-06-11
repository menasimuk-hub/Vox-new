"""Billing lifecycle — credit notes, DD recovery, disputes, monthly fees, pro-rata."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.credit_note import CreditNote
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)

DD_MAX_RETRIES = 3
DD_RETRY_DELAYS_DAYS = (2, 3, 2)  # 2 + 3 + 2 = 7 days total


class BillingLifecycleService:
    # ------------------------------------------------------------------ credit notes / refunds

    @staticmethod
    def issue_wallet_refund(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        currency: str,
        reason: str,
        order_id: str | None = None,
        invoice_id: str | None = None,
        trigger: str | None = None,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        amount = max(0, int(amount_minor or 0))
        if amount <= 0:
            return {"refund_minor": 0}

        from app.services.billing_settings_service import BillingSettingsService
        from app.services.wallet_service import WalletService

        cn_number = BillingSettingsService.allocate_credit_note_number(db)
        credit_note = CreditNote(
            id=str(uuid.uuid4()),
            org_id=org.id,
            invoice_id=invoice_id,
            credit_note_number=cn_number,
            amount_minor=amount,
            currency=str(currency or resolve_org_currency(db, org)).upper()[:3],
            reason=(reason or "Wallet refund")[:512],
            status="issued",
            refund_method="wallet",
            created_by_user_id=created_by_user_id,
            created_at=datetime.utcnow(),
        )
        db.add(credit_note)
        db.flush()

        tx = WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="campaign_refund",
            description=f"Credit note {cn_number}"[:500],
            order_id=order_id,
            invoice_id=invoice_id,
            created_by_user_id=created_by_user_id,
            metadata={"credit_note_id": credit_note.id, "trigger": trigger},
            commit=False,
        )
        db.commit()
        db.refresh(credit_note)
        db.refresh(tx)
        return {
            "credit_note_id": credit_note.id,
            "credit_note_number": cn_number,
            "wallet_transaction_id": tx.id,
            "refund_minor": amount,
        }

    @staticmethod
    def record_bank_refund(
        db: Session,
        *,
        invoice_id: str,
        note: str | None = None,
        created_by_user_id: str | None = None,
    ) -> CreditNote:
        invoice = db.get(BillingInvoice, invoice_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        if (invoice.status or "").lower() in {"refunded", "credited"}:
            raise ValueError("Invoice is already refunded")

        from app.services.billing_settings_service import BillingSettingsService

        amount = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
        cn_number = BillingSettingsService.allocate_credit_note_number(db)
        credit_note = CreditNote(
            id=str(uuid.uuid4()),
            org_id=invoice.org_id,
            invoice_id=invoice.id,
            credit_note_number=cn_number,
            amount_minor=amount,
            currency=str(invoice.currency or "GBP").upper()[:3],
            reason=(note or f"Manual bank refund for {invoice.invoice_number or invoice.id}")[:512],
            status="issued",
            refund_method="bank",
            created_by_user_id=created_by_user_id,
            created_at=datetime.utcnow(),
        )
        invoice.status = "refunded"
        invoice.dispute_note = (note or invoice.dispute_note or "")[:2000] or None
        db.add(credit_note)
        db.add(invoice)
        db.commit()
        db.refresh(credit_note)
        return credit_note

    @staticmethod
    def admin_wallet_credit(
        db: Session,
        *,
        org_id: str,
        amount_minor: int,
        reason: str,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        currency = resolve_org_currency(db, org)
        return BillingLifecycleService.issue_wallet_refund(
            db,
            org,
            amount_minor=amount_minor,
            currency=currency,
            reason=reason or "Admin wallet credit",
            created_by_user_id=created_by_user_id,
            trigger="admin_adjustment",
        )

    # ------------------------------------------------------------------ disputes

    @staticmethod
    def set_invoice_disputed(db: Session, *, invoice_id: str, note: str | None = None) -> BillingInvoice:
        invoice = db.get(BillingInvoice, invoice_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        invoice.disputed = True
        invoice.dispute_note = (note or "").strip() or None
        invoice.status = "disputed"
        invoice.dd_next_retry_at = None
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice

    @staticmethod
    def clear_invoice_dispute(db: Session, *, invoice_id: str, note: str | None = None) -> BillingInvoice:
        invoice = db.get(BillingInvoice, invoice_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        invoice.disputed = False
        if note:
            invoice.dispute_note = note.strip()
        if (invoice.status or "").lower() == "disputed":
            invoice.status = "pending" if invoice.dd_payment_id else "issued"
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice

    # ------------------------------------------------------------------ DD recovery

    @staticmethod
    def find_invoice_by_payment_id(db: Session, payment_id: str) -> BillingInvoice | None:
        pid = str(payment_id or "").strip()
        if not pid:
            return None
        return (
            db.execute(select(BillingInvoice).where(BillingInvoice.dd_payment_id == pid).limit(1))
            .scalars()
            .first()
        )

    @staticmethod
    def _mandate_update_url(db: Session, org_id: str) -> str:
        from app.services.gocardless_service import BillingService

        origin = BillingService._resolved_dashboard_origin()
        return BillingService._dashboard_billing_url(origin, query="billing=update_mandate")

    @staticmethod
    def handle_dd_payment_failure(
        db: Session,
        *,
        payment_id: str,
        org_id: str,
        client_email: str,
        failure_reason: str | None = None,
    ) -> dict[str, Any] | None:
        invoice = BillingLifecycleService.find_invoice_by_payment_id(db, payment_id)
        if invoice is None:
            return None
        if invoice.disputed:
            logger.info("dd_failure_skipped_disputed invoice_id=%s", invoice.id)
            return {"skipped": "disputed", "invoice_id": invoice.id}

        now = datetime.utcnow()
        invoice.status = "failed"
        invoice.dd_status = "failed"
        retry_count = int(invoice.dd_retry_count or 0)
        if retry_count < DD_MAX_RETRIES:
            delay_days = DD_RETRY_DELAYS_DAYS[min(retry_count, len(DD_RETRY_DELAYS_DAYS) - 1)]
            invoice.dd_retry_count = retry_count + 1
            invoice.dd_next_retry_at = now + timedelta(days=delay_days)
        else:
            invoice.dd_next_retry_at = None
            invoice.status = "past_due"
            sub = (
                db.execute(
                    select(Subscription)
                    .where(Subscription.org_id == org_id)
                    .order_by(Subscription.updated_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if sub is not None and sub.status == "active":
                sub.status = "past_due"
                sub.updated_at = now
                db.add(sub)

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return {
            "invoice_id": invoice.id,
            "dd_retry_count": invoice.dd_retry_count,
            "dd_next_retry_at": invoice.dd_next_retry_at.isoformat() if invoice.dd_next_retry_at else None,
            "status": invoice.status,
        }

    @staticmethod
    def handle_dd_payment_success(db: Session, *, payment_id: str) -> BillingInvoice | None:
        invoice = BillingLifecycleService.find_invoice_by_payment_id(db, payment_id)
        if invoice is None:
            return None
        if (invoice.status or "").lower() == "paid":
            return invoice

        invoice.status = "paid"
        invoice.dd_status = "confirmed"
        invoice.dd_retry_count = 0
        invoice.dd_next_retry_at = None
        db.add(invoice)

        sub = (
            db.execute(
                select(Subscription)
                .where(Subscription.org_id == invoice.org_id)
                .order_by(Subscription.updated_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if sub is not None and sub.status == "past_due":
            sub.status = "active"
            sub.updated_at = datetime.utcnow()
            db.add(sub)
        db.commit()
        db.refresh(invoice)

        try:
            from app.services.billing_event_email_service import BillingEventEmailService

            BillingEventEmailService.send_payment_receipt(db, invoice=invoice)
        except Exception:
            logger.exception("dd_payment_receipt_failed invoice_id=%s", invoice.id)
        return invoice

    @staticmethod
    def retry_due_dd_invoices(db: Session, *, as_of: datetime | None = None) -> dict[str, int]:
        now = as_of or datetime.utcnow()
        stats = {"attempted": 0, "submitted": 0, "skipped": 0, "exhausted": 0}

        due = list(
            db.execute(
                select(BillingInvoice).where(
                    BillingInvoice.dd_next_retry_at.is_not(None),
                    BillingInvoice.dd_next_retry_at <= now,
                    BillingInvoice.disputed.is_(False),
                    BillingInvoice.status.in_(["failed", "pending", "collecting", "past_due"]),
                )
            )
            .scalars()
            .all()
        )

        from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
        from app.services.usage_wallet_service import UsageWalletService

        for invoice in due:
            if int(invoice.dd_retry_count or 0) > DD_MAX_RETRIES:
                stats["exhausted"] += 1
                invoice.dd_next_retry_at = None
                invoice.status = "past_due"
                db.add(invoice)
                continue

            stats["attempted"] += 1
            amount = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
            if amount <= 0:
                stats["skipped"] += 1
                continue

            email = invoice.client_email or UsageWalletService.get_org_billing_email(db, invoice.org_id) or ""
            try:
                payment = BillingService.collect_mandate_payment(
                    db,
                    org_id=invoice.org_id,
                    amount_pence=amount,
                    description=str(invoice.description or "VOXBULK invoice retry")[:255],
                    currency=invoice.currency or "GBP",
                    metadata={"invoice_id": invoice.id},
                )
            except (GoCardlessConfigError, GoCardlessProviderError):
                logger.warning("dd_retry_collect_failed invoice_id=%s", invoice.id)
                stats["skipped"] += 1
                continue

            if payment is None:
                stats["skipped"] += 1
                continue

            invoice.dd_payment_id = str(payment.get("payment_id") or invoice.dd_payment_id or "")
            invoice.dd_status = str(payment.get("status") or "pending_submission")
            invoice.payment_reference = invoice.dd_payment_id
            invoice.status = "collecting"
            invoice.dd_next_retry_at = None
            db.add(invoice)
            stats["submitted"] += 1

        db.commit()
        return stats

    # ------------------------------------------------------------------ monthly subscription billing

    @staticmethod
    def process_due_monthly_billing(db: Session, *, as_of: datetime | None = None) -> dict[str, int]:
        now = as_of or datetime.utcnow()
        stats = {"checked": 0, "invoiced": 0, "skipped": 0, "trial_converted": 0}

        subs = list(
            db.execute(
                select(Subscription).where(
                    Subscription.status.in_(["active", "trial"]),
                    Subscription.current_period_end.is_not(None),
                    Subscription.current_period_end <= now,
                )
            )
            .scalars()
            .all()
        )

        from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        for sub in subs:
            stats["checked"] += 1
            from app.services.subscription_cancellation_service import (
                CANCELLATION_CANCELLED,
                CANCELLATION_SCHEDULED,
                SubscriptionCancellationService,
            )

            cancel_st = str(sub.cancellation_status or "none").lower()
            if cancel_st in {CANCELLATION_CANCELLED, CANCELLATION_SCHEDULED}:
                stats["skipped"] += 1
                continue
            from app.models.billing_refund_review import BillingRefundReview

            latest_review = (
                db.execute(
                    select(BillingRefundReview)
                    .where(BillingRefundReview.org_id == sub.org_id)
                    .order_by(BillingRefundReview.requested_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if latest_review and str(latest_review.review_status or "").lower() in {"approved", "completed"}:
                stats["skipped"] += 1
                continue

            org = db.get(Organisation, sub.org_id)
            plan = db.get(Plan, sub.plan_id)
            if org is None or plan is None:
                stats["skipped"] += 1
                continue
            if str(plan.code or "").lower() == "payg":
                stats["skipped"] += 1
                continue

            if (
                str(sub.payment_provider or "").lower() == "gocardless"
                and str(sub.external_subscription_id or "").strip()
            ):
                stats["skipped"] += 1
                continue

            email = UsageWalletService.get_org_billing_email(db, sub.org_id) or (org.contact_email or "")
            if not email:
                stats["skipped"] += 1
                continue

            rates = PlanPriceService.rates_for_org(db, org, plan=plan)
            currency = str(rates["currency"])
            monthly_minor = int(rates.get("monthly_price_minor") or plan.price_gbp_pence or 0)
            if monthly_minor <= 0:
                stats["skipped"] += 1
                continue

            period_key = sub.current_period_end.strftime("%Y%m%d") if sub.current_period_end else now.strftime("%Y%m%d")
            external_id = f"sub-monthly:{sub.id}:{period_key}"
            existing = InvoiceService.get_by_external(db, provider="gocardless", external_invoice_id=external_id)
            if existing is not None:
                stats["skipped"] += 1
                BillingLifecycleService._advance_subscription_period(db, sub, plan)
                continue

            desc = f"{plan.name} — monthly subscription"
            invoice = InvoiceService.create_from_payment(
                db,
                org_id=sub.org_id,
                client_email=email,
                subtotal_pence=monthly_minor,
                currency=currency,
                description=desc,
                provider="gocardless",
                external_invoice_id=external_id,
                payment_method="gocardless",
                status="pending",
                line_items=[
                    {
                        "description": desc,
                        "quantity": 1,
                        "unit_pence": monthly_minor,
                        "total_pence": monthly_minor,
                    }
                ],
                kind="subscription",
            )

            if sub.status == "trial":
                sub.status = "active"
                stats["trial_converted"] += 1

            try:
                payment = BillingService.collect_mandate_payment(
                    db,
                    org_id=sub.org_id,
                    amount_pence=monthly_minor,
                    description=desc,
                    currency=currency,
                    metadata={"invoice_id": invoice.id, "billing": "subscription"},
                )
                if payment is not None:
                    invoice.dd_payment_id = str(payment.get("payment_id") or "")
                    invoice.dd_status = str(payment.get("status") or "pending_submission")
                    invoice.payment_reference = invoice.dd_payment_id
                    invoice.status = "collecting"
            except (GoCardlessConfigError, GoCardlessProviderError):
                invoice.dd_status = "submission_failed"
                invoice.status = "pending"

            db.add(invoice)
            db.commit()
            db.refresh(invoice)

            try:
                from app.services.billing_event_email_service import BillingEventEmailService

                BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
            except Exception:
                logger.exception("monthly_invoice_email_failed invoice_id=%s", invoice.id)

            BillingLifecycleService._advance_subscription_period(db, sub, plan)
            stats["invoiced"] += 1

        return stats

    @staticmethod
    def _advance_subscription_period(db: Session, sub: Subscription, plan: Plan) -> None:
        from app.services.usage_wallet_service import UsageWalletService

        now = datetime.utcnow()
        next_end = (sub.current_period_end or now) + timedelta(days=30)
        sub.current_period_end = next_end
        sub.updated_at = now

        org = db.get(Organisation, sub.org_id)
        from app.services.billing_finance_service import BillingFinanceService

        BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan, commit=False)

        if sub.pending_plan_id and sub.pending_plan_id != sub.plan_id:
            pending = db.get(Plan, sub.pending_plan_id)
            if pending is not None:
                sub.plan_id = pending.id
                sub.pending_plan_id = None
                plan = pending

        db.add(sub)
        db.commit()
        UsageWalletService.sync_plan_limits(db, org_id=sub.org_id, plan=plan, subscription=sub)

        row = UsageWalletService.get_current(db, sub.org_id)
        if row is not None and row.period_end <= now:
            UsageWalletService.rollover_due_periods(db, as_of=now)

    # ------------------------------------------------------------------ pro-rata upgrade

    @staticmethod
    def calculate_pro_rata_minor(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        old_plan: Plan,
        new_plan: Plan,
    ) -> int:
        rates_old = PlanPriceService.rates_for_org(db, org, plan=old_plan)
        rates_new = PlanPriceService.rates_for_org(db, org, plan=new_plan)
        old_monthly = int(rates_old.get("monthly_price_minor") or old_plan.price_gbp_pence or 0)
        new_monthly = int(rates_new.get("monthly_price_minor") or new_plan.price_gbp_pence or 0)
        delta = max(0, new_monthly - old_monthly)
        if delta <= 0:
            return 0

        period_end = sub.current_period_end or (datetime.utcnow() + timedelta(days=30))
        period_start = period_end - timedelta(days=30)
        now = datetime.utcnow()
        if now >= period_end:
            return delta

        total_seconds = max(1, int((period_end - period_start).total_seconds()))
        remaining_seconds = max(0, int((period_end - now).total_seconds()))
        return max(0, int(delta * remaining_seconds / total_seconds))

    @staticmethod
    def apply_upgrade_with_pro_rata(
        db: Session,
        *,
        org_id: str,
        new_plan: Plan,
        old_plan: Plan,
        sub: Subscription,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")

        pro_rata = BillingLifecycleService.calculate_pro_rata_minor(db, org=org, sub=sub, old_plan=old_plan, new_plan=new_plan)
        invoice_id = None
        if pro_rata > 0:
            from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
            from app.services.invoice_service import InvoiceService
            from app.services.usage_wallet_service import UsageWalletService

            email = UsageWalletService.get_org_billing_email(db, org_id) or (org.contact_email or "")
            currency = PlanPriceService.rates_for_org(db, org, plan=new_plan)["currency"]
            desc = f"Pro-rata upgrade to {new_plan.name}"
            external_id = f"pro-rata:{sub.id}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            invoice = InvoiceService.create_from_payment(
                db,
                org_id=org_id,
                client_email=email,
                subtotal_pence=pro_rata,
                currency=str(currency),
                description=desc,
                provider="gocardless",
                external_invoice_id=external_id,
                payment_method="gocardless",
                status="pending",
                line_items=[
                    {
                        "description": desc,
                        "quantity": 1,
                        "unit_pence": pro_rata,
                        "total_pence": pro_rata,
                    }
                ],
                kind="pro_rata",
            )
            invoice_id = invoice.id
            try:
                payment = BillingService.collect_mandate_payment(
                    db,
                    org_id=org_id,
                    amount_pence=pro_rata,
                    description=desc,
                    currency=str(currency),
                    metadata={"invoice_id": invoice.id},
                )
                if payment is not None:
                    invoice.dd_payment_id = str(payment.get("payment_id") or "")
                    invoice.dd_status = str(payment.get("status") or "pending_submission")
                    invoice.payment_reference = invoice.dd_payment_id
                    invoice.status = "collecting"
                    db.add(invoice)
                    db.commit()
            except (GoCardlessConfigError, GoCardlessProviderError):
                invoice.dd_status = "submission_failed"
                db.add(invoice)
                db.commit()

            try:
                from app.services.billing_event_email_service import BillingEventEmailService

                BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
            except Exception:
                logger.exception("pro_rata_invoice_email_failed invoice_id=%s", invoice.id)

        now = datetime.utcnow()
        sub.plan_id = new_plan.id
        sub.pending_plan_id = None
        sub.updated_at = now
        db.add(sub)
        db.commit()

        from app.services.usage_wallet_service import UsageWalletService

        UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=new_plan, subscription=sub)
        return {"pro_rata_minor": pro_rata, "invoice_id": invoice_id, "plan_id": new_plan.id}

    @staticmethod
    def change_subscription_plan(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
    ) -> tuple[Subscription, Plan, str, dict[str, Any] | None]:
        from app.services.gocardless_service import BillingService

        sub = BillingService.get_subscription(db, org_id)
        old_plan = None
        if sub is not None:
            old_plan = db.get(Plan, sub.plan_id)

        new_plan = None
        if plan_id:
            new_plan = db.get(Plan, plan_id)
        if new_plan is None and plan_code:
            new_plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if new_plan is None:
            raise ValueError("Unknown plan")

        from app.models.organisation import Organisation
        from app.services.plan_price_service import PlanPriceService

        org = db.get(Organisation, org_id)
        old_rates = (
            PlanPriceService.rates_for_org(db, org, plan=old_plan) if old_plan is not None else {}
        )
        new_rates = PlanPriceService.rates_for_org(db, org, plan=new_plan)
        old_price = int(old_rates.get("monthly_price_minor") or old_plan.price_gbp_pence or 0) if old_plan else 0
        new_price = int(new_rates.get("monthly_price_minor") or new_plan.price_gbp_pence or 0)
        if new_price > old_price:
            direction = "upgrade"
        elif new_price < old_price:
            direction = "downgrade"
        else:
            direction = "same"

        extra: dict[str, Any] | None = None
        if sub is not None and sub.status in {"active", "trial"} and sub.payment_provider == "gocardless":
            if direction == "upgrade" and old_plan is not None:
                extra = BillingLifecycleService.apply_upgrade_with_pro_rata(
                    db, org_id=org_id, new_plan=new_plan, old_plan=old_plan, sub=sub
                )
                db.refresh(sub)
                return sub, new_plan, direction, extra
            if direction == "downgrade":
                sub.pending_plan_id = new_plan.id
                sub.updated_at = datetime.utcnow()
                db.add(sub)
                db.commit()
                db.refresh(sub)
                return sub, new_plan, direction, {"pending_plan_id": new_plan.id}

        sub, plan, dir2 = BillingService.change_plan(db, org_id=org_id, plan_id=plan_id, plan_code=plan_code)
        return sub, plan, dir2, extra
