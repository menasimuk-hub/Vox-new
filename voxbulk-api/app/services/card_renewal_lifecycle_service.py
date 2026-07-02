"""Failed card subscription renewals — retry schedule and payment-failed emails."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_lifecycle_service import DD_MAX_RETRIES, DD_RETRY_DELAYS_DAYS
from app.services.invoice_service import InvoiceService
from app.services.plan_price_service import PlanPriceService
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)

CARD_RENEWAL_PROVIDERS = frozenset({"stripe", "airwallex"})


class CardRenewalLifecycleService:
    @staticmethod
    def renewal_external_id(sub_id: str, period_key: str) -> str:
        return f"sub-renewal:{sub_id}:{period_key}"

    @staticmethod
    def parse_renewal_external_id(external_id: str) -> tuple[str | None, str | None]:
        raw = str(external_id or "").strip()
        if not raw.startswith("sub-renewal:"):
            return None, None
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return None, None
        return parts[1] or None, parts[2] or None

    @staticmethod
    def ensure_renewal_invoice(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan,
        provider: str,
        period_key: str,
        amount_minor: int,
        currency: str,
        payment_reference: str | None = None,
        status: str = "pending",
    ) -> BillingInvoice:
        ext_inv = CardRenewalLifecycleService.renewal_external_id(sub.id, period_key)
        existing = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=ext_inv)
        if existing is not None:
            return existing

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        interval_label = "yearly" if str(sub.billing_interval or "") == "yearly" else "monthly"
        desc = f"{plan.name} — {interval_label} subscription renewal"
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org.id,
            client_email=email or "billing@voxbulk.local",
            subtotal_pence=amount_minor,
            currency=currency,
            description=desc,
            provider=provider,
            external_invoice_id=ext_inv,
            payment_reference=payment_reference,
            payment_method=provider,
            status=status,
            line_items=[
                {
                    "description": desc,
                    "quantity": 1,
                    "unit_pence": amount_minor,
                    "total_pence": amount_minor,
                }
            ],
            kind="subscription",
        )
        return invoice

    @staticmethod
    def handle_renewal_failure(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan,
        provider: str,
        period_key: str,
        amount_minor: int,
        currency: str,
        payment_reference: str | None = None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        invoice = CardRenewalLifecycleService.ensure_renewal_invoice(
            db,
            org=org,
            sub=sub,
            plan=plan,
            provider=provider,
            period_key=period_key,
            amount_minor=amount_minor,
            currency=currency,
            payment_reference=payment_reference,
            status="failed",
        )
        if invoice.disputed:
            return {"skipped": "disputed", "invoice_id": invoice.id}

        now = datetime.utcnow()
        invoice.status = "failed"
        invoice.dd_status = "failed"
        if payment_reference:
            invoice.payment_reference = payment_reference
        retry_count = int(invoice.dd_retry_count or 0)
        if retry_count < DD_MAX_RETRIES:
            delay_days = DD_RETRY_DELAYS_DAYS[min(retry_count, len(DD_RETRY_DELAYS_DAYS) - 1)]
            invoice.dd_retry_count = retry_count + 1
            invoice.dd_next_retry_at = now + timedelta(days=delay_days)
        else:
            invoice.dd_next_retry_at = None
            invoice.status = "past_due"
            if str(sub.status or "").lower() == "active":
                sub.status = "past_due"
                sub.updated_at = now
                db.add(sub)

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        CardRenewalLifecycleService._send_failure_email(
            db,
            org=org,
            invoice=invoice,
            plan=plan,
            failure_reason=failure_reason,
        )

        return {
            "invoice_id": invoice.id,
            "dd_retry_count": invoice.dd_retry_count,
            "dd_next_retry_at": invoice.dd_next_retry_at.isoformat() if invoice.dd_next_retry_at else None,
            "status": invoice.status,
        }

    @staticmethod
    def mark_renewal_paid(db: Session, *, sub: Subscription, provider: str, period_key: str) -> None:
        ext_inv = CardRenewalLifecycleService.renewal_external_id(sub.id, period_key)
        invoice = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=ext_inv)
        now = datetime.utcnow()
        if invoice is not None:
            invoice.status = "paid"
            invoice.dd_status = "confirmed"
            invoice.dd_retry_count = 0
            invoice.dd_next_retry_at = None
            db.add(invoice)
        if str(sub.status or "").lower() == "past_due":
            sub.status = "active"
            sub.updated_at = now
            db.add(sub)
        db.commit()

    @staticmethod
    def _send_failure_email(
        db: Session,
        *,
        org: Organisation,
        invoice: BillingInvoice,
        plan: Plan,
        failure_reason: str | None,
    ) -> None:
        try:
            from app.services.billing_currency import money_display
            from app.services.product_email_triggers import ProductEmailTriggers

            amount = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
            currency = str(invoice.currency or org.billing_currency or "GBP")
            ProductEmailTriggers.notify_payment_failed(
                db,
                to_email=invoice.client_email,
                extra_variables={
                    "plan_name": plan.name,
                    "amount_due": money_display(amount, currency),
                    "payment_status": invoice.status or "failed",
                    "failure_reason": failure_reason or "Card payment declined",
                    "org_name": org.name or "",
                },
            )
        except Exception:
            logger.exception("card_renewal_failure_email_failed invoice_id=%s", invoice.id)

    @staticmethod
    def retry_due_renewals(db: Session, *, as_of: datetime | None = None) -> dict[str, int]:
        now = as_of or datetime.utcnow()
        stats = {"attempted": 0, "submitted": 0, "skipped": 0, "exhausted": 0, "paid": 0}

        due = list(
            db.execute(
                select(BillingInvoice).where(
                    BillingInvoice.provider.in_(tuple(CARD_RENEWAL_PROVIDERS)),
                    BillingInvoice.kind == "subscription",
                    BillingInvoice.external_invoice_id.like("sub-renewal:%"),
                    BillingInvoice.dd_next_retry_at.is_not(None),
                    BillingInvoice.dd_next_retry_at <= now,
                    BillingInvoice.disputed.is_(False),
                    BillingInvoice.status.in_(["failed", "pending", "past_due"]),
                )
            )
            .scalars()
            .all()
        )

        for invoice in due:
            if int(invoice.dd_retry_count or 0) > DD_MAX_RETRIES:
                stats["exhausted"] += 1
                invoice.dd_next_retry_at = None
                invoice.status = "past_due"
                db.add(invoice)
                continue

            sub_id, period_key = CardRenewalLifecycleService.parse_renewal_external_id(invoice.external_invoice_id)
            if not sub_id or not period_key:
                stats["skipped"] += 1
                continue

            sub = db.get(Subscription, sub_id)
            org = db.get(Organisation, invoice.org_id)
            plan = db.get(Plan, sub.plan_id) if sub else None
            if sub is None or org is None or plan is None:
                stats["skipped"] += 1
                continue

            provider = str(invoice.provider or "").lower()
            amount = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
            currency = str(invoice.currency or org.billing_currency or "GBP")
            if amount <= 0:
                _currency, amount, _ = PlanPriceService.billing_amount_for_org(db, org, plan, sub.billing_interval)
                currency = _currency

            stats["attempted"] += 1
            try:
                if provider == "airwallex":
                    from app.services.airwallex_billing_service import AirwallexBillingError, AirwallexBillingService

                    if not AirwallexBillingService.is_managed_subscription(sub):
                        stats["skipped"] += 1
                        continue
                    charge = AirwallexBillingService.charge_renewal(
                        db,
                        org=org,
                        sub=sub,
                        plan=plan,
                        amount_minor=amount,
                        currency=currency,
                        period_key=period_key,
                    )
                    status = str(charge.get("status") or "").upper()
                    if status == "SUCCEEDED":
                        AirwallexBillingService.handle_renewal_payment_success(
                            db, org=org, intent=charge.get("intent") or {}
                        )
                        stats["paid"] += 1
                        stats["submitted"] += 1
                    else:
                        CardRenewalLifecycleService.handle_renewal_failure(
                            db,
                            org=org,
                            sub=sub,
                            plan=plan,
                            provider=provider,
                            period_key=period_key,
                            amount_minor=amount,
                            currency=currency,
                            payment_reference=charge.get("payment_intent_id"),
                            failure_reason=f"Airwallex status {status}",
                        )
                elif provider == "stripe":
                    from app.services.stripe_billing_service import StripeBillingError, StripeBillingService

                    if not StripeBillingService.is_managed_subscription(sub):
                        stats["skipped"] += 1
                        continue
                    charge = StripeBillingService.charge_renewal(
                        db,
                        org=org,
                        sub=sub,
                        plan=plan,
                        amount_minor=amount,
                        currency=currency,
                        period_key=period_key,
                    )
                    status = str(charge.get("status") or "").lower()
                    if status == "succeeded":
                        StripeBillingService.handle_renewal_payment_success(
                            db, org=org, intent=charge.get("intent") or {}
                        )
                        stats["paid"] += 1
                        stats["submitted"] += 1
                    else:
                        CardRenewalLifecycleService.handle_renewal_failure(
                            db,
                            org=org,
                            sub=sub,
                            plan=plan,
                            provider=provider,
                            period_key=period_key,
                            amount_minor=amount,
                            currency=currency,
                            payment_reference=charge.get("payment_intent_id"),
                            failure_reason=f"Stripe status {status}",
                        )
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                from app.services.airwallex_billing_service import AirwallexBillingError
                from app.services.stripe_billing_service import StripeBillingError

                if isinstance(exc, (AirwallexBillingError, StripeBillingError)):
                    CardRenewalLifecycleService.handle_renewal_failure(
                        db,
                        org=org,
                        sub=sub,
                        plan=plan,
                        provider=provider,
                        period_key=period_key,
                        amount_minor=amount,
                        currency=currency,
                        failure_reason=str(exc),
                    )
                else:
                    logger.exception("card_renewal_retry_failed invoice_id=%s", invoice.id)
                    CardRenewalLifecycleService.handle_renewal_failure(
                        db,
                        org=org,
                        sub=sub,
                        plan=plan,
                        provider=provider,
                        period_key=period_key,
                        amount_minor=amount,
                        currency=currency,
                        failure_reason=str(exc)[:500],
                    )

        db.commit()
        return stats

    @staticmethod
    def handle_renewal_webhook_failure(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
        provider: str,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        meta = intent.get("metadata") or {}
        sub_id = str(meta.get("voxbulk_subscription_id") or "").strip()
        period_key = str(meta.get("voxbulk_period_key") or "").strip()
        pid = str(intent.get("id") or "").strip()
        sub = db.get(Subscription, sub_id) if sub_id else None
        if sub is None:
            return {"ok": True, "ignored": True, "reason": "subscription_not_found"}
        plan = db.get(Plan, sub.plan_id)
        if plan is None:
            return {"ok": True, "ignored": True, "reason": "plan_not_found"}

        if not period_key and sub.current_period_end:
            period_key = sub.current_period_end.strftime("%Y%m%d")

        amount_minor = 0
        if provider == "stripe":
            from app.services.stripe_billing_service import StripeBillingService

            amount_minor = StripeBillingService.intent_amount_minor(intent)
        else:
            from app.services.airwallex_billing_service import AirwallexBillingService

            amount_minor = AirwallexBillingService.intent_amount_minor(intent)

        currency = str(intent.get("currency") or sub.billing_currency or "GBP").upper()
        if amount_minor <= 0:
            _currency, amount_minor, _ = PlanPriceService.billing_amount_for_org(
                db, org, plan, sub.billing_interval
            )
            currency = _currency

        result = CardRenewalLifecycleService.handle_renewal_failure(
            db,
            org=org,
            sub=sub,
            plan=plan,
            provider=provider,
            period_key=period_key or "unknown",
            amount_minor=amount_minor,
            currency=currency,
            payment_reference=pid or None,
            failure_reason=failure_reason or "Card renewal payment failed",
        )
        return {"ok": True, "renewal_failed": True, **result}
