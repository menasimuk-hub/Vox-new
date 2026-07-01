"""Airwallex recurring subscription checkout (Gulf / non-GoCardless markets)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.airwallex_payment_service import AirwallexPaymentService, AirwallexProviderError
from app.services.plan_price_service import PlanPriceService


class AirwallexSubscriptionError(ValueError):
    pass


class AirwallexSubscriptionService:
    @staticmethod
    def start_subscription_checkout(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        user_email: str,
        billing_interval: str | None = None,
        service_code: str = "voxbulk",
    ) -> dict[str, Any]:
        if not AirwallexPaymentService.is_available(db):
            raise AirwallexSubscriptionError("Airwallex is not configured for subscriptions.")
        currency, amount_minor, interval = PlanPriceService.billing_amount_for_org(
            db,
            org,
            plan,
            billing_interval,
        )
        if amount_minor <= 0:
            raise AirwallexSubscriptionError("Plan price is not configured for your billing currency.")

        intent = AirwallexPaymentService.create_topup_intent(db, org, amount_minor=amount_minor)
        return {
            "provider": "airwallex",
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
        payment_provider: str = "airwallex",
        service_code: str = "voxbulk",
        billing_interval: str = "monthly",
    ) -> Subscription:
        """Create or update local subscription after successful Airwallex payment."""
        currency, amount_minor, interval = PlanPriceService.billing_amount_for_org(db, org, plan, billing_interval)
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            service_code=service_code,
            payment_provider=payment_provider,
            billing_currency=currency,
            billing_interval=interval or billing_interval,
            amount_next_payment_minor=int(amount_minor or 0),
            external_subscription_id=str(provider_reference or "")[:255] or None,
            first_payment_at=now,
            current_period_end=now.replace(day=28) if now.day > 28 else now,  # placeholder; lifecycle sync adjusts
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
            return AirwallexPaymentService.create_topup_intent(db, org, amount_minor=amount_minor)
        except AirwallexProviderError:
            return None
