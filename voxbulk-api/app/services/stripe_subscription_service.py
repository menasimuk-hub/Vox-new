"""Stripe Billing fallback for subscriptions when Airwallex / GoCardless unavailable."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.card_subscription_activation_service import CardSubscriptionActivationService
from app.services.plan_price_service import PlanPriceService
from app.services.stripe_payment_service import StripePaymentService, StripeProviderError

logger = logging.getLogger(__name__)


class StripeSubscriptionError(ValueError):
    pass


class StripeSubscriptionService:
    @staticmethod
    def start_subscription_checkout(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        user_email: str = "",
        billing_interval: str | None = None,
        service_code: str = "voxbulk",
    ) -> dict[str, Any]:
        if not StripePaymentService.is_available(db):
            raise StripeSubscriptionError("Stripe is not configured for subscriptions.")
        currency, amount_minor, interval = PlanPriceService.billing_amount_for_org(
            db,
            org,
            plan,
            billing_interval,
        )
        if amount_minor <= 0:
            raise StripeSubscriptionError("Plan price is not configured for your billing currency.")
        intent = StripePaymentService.create_subscription_checkout_intent(
            db,
            org,
            amount_minor=amount_minor,
            plan_id=plan.id,
            billing_interval=interval,
            service_code=service_code,
            customer_email=user_email,
        )
        return {
            "provider": "stripe",
            "currency": currency,
            "amount_minor": amount_minor,
            "billing_interval": interval,
            "client_secret": intent.get("client_secret"),
            "intent_id": intent.get("payment_intent_id") or intent.get("intent_id"),
            "checkout": intent,
            "plan_id": plan.id,
            "service_code": service_code,
        }

    @staticmethod
    def activate_from_payment(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        provider_reference: str,
        service_code: str = "voxbulk",
        billing_interval: str = "monthly",
    ) -> Subscription:
        return CardSubscriptionActivationService.activate_from_payment(
            db,
            org=org,
            plan=plan,
            provider="stripe",
            payment_intent_id=provider_reference,
            billing_interval=billing_interval,
            service_code=service_code,
        )

    @staticmethod
    def sync_checkout_credentials(db: Session, sub: Subscription, *, payment_intent_id: str) -> Subscription:
        from app.services.stripe_billing_service import StripeBillingService

        return StripeBillingService.sync_credentials_from_intent(db, sub, payment_intent_id=payment_intent_id)

    @staticmethod
    def process_due_renewal(
        db: Session,
        *,
        sub: Subscription,
        org: Organisation,
        plan: Plan,
        as_of: datetime | None = None,
    ) -> dict[str, str]:
        from app.services.billing_lifecycle_service import BillingLifecycleService
        from app.services.invoice_service import InvoiceService
        from app.services.stripe_billing_service import StripeBillingError, StripeBillingService
        from app.services.usage_wallet_service import UsageWalletService

        stats = {"renewal_charged": "0", "renewal_skipped": "0", "renewal_failed": "0"}
        if not StripeBillingService.is_managed_subscription(sub):
            stats["renewal_skipped"] = "1"
            return stats

        now = as_of or datetime.utcnow()
        email = UsageWalletService.get_org_billing_email(db, sub.org_id) or (org.contact_email or "")
        if not email:
            stats["renewal_skipped"] = "1"
            return stats

        currency, amount_minor, _interval = PlanPriceService.billing_amount_for_org(
            db, org, plan, sub.billing_interval
        )
        if amount_minor <= 0:
            stats["renewal_skipped"] = "1"
            return stats

        period_key = sub.current_period_end.strftime("%Y%m%d") if sub.current_period_end else now.strftime("%Y%m%d")
        ext_inv = f"sub-renewal:{sub.id}:{period_key}"
        existing = InvoiceService.get_by_external(db, provider="stripe", external_invoice_id=ext_inv)
        if existing is not None and str(existing.status or "").lower() == "paid":
            BillingLifecycleService._advance_subscription_period(db, sub, plan)
            stats["renewal_skipped"] = "1"
            return stats

        try:
            charge = StripeBillingService.charge_renewal(
                db,
                org=org,
                sub=sub,
                plan=plan,
                amount_minor=amount_minor,
                currency=currency,
                period_key=period_key,
            )
        except (StripeBillingError, StripeProviderError) as exc:
            logger.warning("stripe_renewal_failed sub_id=%s err=%s", sub.id, exc)
            from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService

            CardRenewalLifecycleService.handle_renewal_failure(
                db,
                org=org,
                sub=sub,
                plan=plan,
                provider="stripe",
                period_key=period_key,
                amount_minor=amount_minor,
                currency=currency,
                failure_reason=str(exc),
            )
            stats["renewal_failed"] = "1"
            return stats

        status = str(charge.get("status") or "").lower()
        if status == "succeeded":
            StripeBillingService.handle_renewal_payment_success(
                db,
                org=org,
                intent=charge.get("intent")
                or {
                    "id": charge.get("payment_intent_id"),
                    "metadata": {
                        "voxbulk_subscription_id": sub.id,
                        "voxbulk_period_key": period_key,
                    },
                    "currency": currency.lower(),
                    "amount_received": amount_minor,
                },
            )
            stats["renewal_charged"] = "1"
        else:
            from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService

            CardRenewalLifecycleService.handle_renewal_failure(
                db,
                org=org,
                sub=sub,
                plan=plan,
                provider="stripe",
                period_key=period_key,
                amount_minor=amount_minor,
                currency=currency,
                payment_reference=charge.get("payment_intent_id"),
                failure_reason=f"Stripe status {status}",
            )
            stats["renewal_failed"] = "1"
        return stats

    @staticmethod
    def collect_overage(
        db: Session,
        *,
        org: Organisation,
        amount_minor: int,
        currency: str,
        description: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if amount_minor <= 0:
            return None
        try:
            return StripePaymentService.create_topup_intent(db, org, amount_minor=amount_minor)
        except StripeProviderError:
            return None
