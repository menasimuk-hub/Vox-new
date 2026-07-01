"""Stripe Billing fallback for subscriptions when Airwallex / GoCardless unavailable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.plan_price_service import PlanPriceService
from app.services.stripe_payment_service import StripePaymentService, StripeProviderError


class StripeSubscriptionError(ValueError):
    pass


class StripeSubscriptionService:
    @staticmethod
    def start_subscription_checkout(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
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
        intent = StripePaymentService.create_topup_intent(db, org, amount_minor=amount_minor)
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
        currency, amount_minor, interval = PlanPriceService.billing_amount_for_org(db, org, plan, billing_interval)
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            service_code=service_code,
            payment_provider="stripe",
            billing_currency=currency,
            billing_interval=interval or billing_interval,
            amount_next_payment_minor=int(amount_minor or 0),
            external_subscription_id=str(provider_reference or "")[:255] or None,
            first_payment_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        from app.services.usage_wallet_service import UsageWalletService

        UsageWalletService.bootstrap_from_plan(db, org_id=org.id, subscription=sub)
        return sub

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
