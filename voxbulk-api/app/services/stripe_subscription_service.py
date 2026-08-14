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
        from app.services.billing_currency import charge_currency_for_org
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        charge_currency_for_org(db, org, persist=True)
        try:
            CustomPackagesService.assert_checkout_allowed(db, org, plan)
        except CustomPackagesError as e:
            raise StripeSubscriptionError(str(e)) from e
        currency, amount_minor, interval = PlanPriceService.billing_amount_for_org(
            db,
            org,
            plan,
            billing_interval,
        )
        if amount_minor <= 0:
            raise StripeSubscriptionError("Plan price is not configured for your billing currency.")
        from app.services.promo_discount_service import PromoDiscountService

        service_kind = "customer_feedback" if str(service_code or "").lower() in {
            "customer_feedback",
            "feedback",
        } else "smart_card" if str(service_code or "").lower() in {
            "smart_card",
            "smartcard",
        } else "voxbulk"
        discounted = PromoDiscountService.apply_and_consume(
            db, org_id=org.id, service_kind=service_kind, amount_minor=amount_minor
        )
        trial_days = int(discounted.get("trial_days") or 0)
        amount_minor = int(discounted["amount_minor"])
        if trial_days > 0 or amount_minor <= 0:
            # Trial or 100% discount — activate without card charge.
            from datetime import timedelta

            from app.services.billing_access_service import BillingAccessService
            from app.services.usage_wallet_service import UsageWalletService

            now = datetime.utcnow()
            period_days = trial_days if trial_days > 0 else (365 if interval == "yearly" else 30)
            sub = BillingAccessService.get_subscription(db, org.id, service_code=service_code)
            if sub is None:
                sub = Subscription(org_id=org.id, plan_id=plan.id, service_code=service_code, created_at=now)
            sub.plan_id = plan.id
            sub.status = "trial" if trial_days > 0 else "active"
            sub.payment_provider = "promo_discount"
            sub.billing_currency = currency
            sub.billing_interval = interval
            catalog = int(discounted.get("original_amount_minor") or amount_minor or 0)
            sub.amount_next_payment_minor = catalog if trial_days > 0 else 0
            sub.external_subscription_id = f"promo-{'trial' if trial_days else 'discount'}-{org.id[:8]}"[:255]
            sub.current_period_end = now + timedelta(days=period_days)
            sub.updated_at = now
            db.add(sub)
            db.commit()
            db.refresh(sub)
            if str(service_code or "").lower() not in {"smart_card", "customer_feedback", "feedback"}:
                try:
                    UsageWalletService.bootstrap_from_plan(db, org_id=org.id, subscription=sub)
                except Exception:
                    logger.exception("promo trial wallet bootstrap failed org=%s", org.id)
            return {
                "provider": "promo_discount",
                "paid": True,
                "currency": currency,
                "amount_minor": 0,
                "billing_interval": interval,
                "plan_id": plan.id,
                "service_code": service_code,
                "subscription_id": sub.id,
                "promo_discount_applied": True,
                "trial_days": trial_days,
            }
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
            "promo_discount_applied": bool(discounted.get("discount_applied")),
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

        pid = str(payment_intent_id or "").strip()
        if pid.startswith("seti_"):
            return StripeBillingService.sync_credentials_from_setup_intent(db, sub, setup_intent_id=pid)
        return StripeBillingService.sync_credentials_from_intent(db, sub, payment_intent_id=pid)

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

        currency, amount_minor = PlanPriceService.subscription_charge_amount_for_org(
            db, org, plan, sub
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
