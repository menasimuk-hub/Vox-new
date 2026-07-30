"""Smart Card QR seat billing — quantity × yearly unit price."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.smart_card import SMART_CARD_SERVICE_CODE, SmartCardPackage
from app.models.subscription import Subscription
from app.services.card_subscription_activation_service import (
    CardSubscriptionActivationError,
    CardSubscriptionActivationService,
)
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)


class SmartCardBillingError(ValueError):
    pass


class SmartCardBillingService:
    @staticmethod
    def _validate_plan(db: Session, plan_id: str) -> tuple[Plan, SmartCardPackage]:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise SmartCardBillingError("Unknown plan")
        if str(plan.service_kind or "") != SMART_CARD_SERVICE_CODE:
            raise SmartCardBillingError("Plan is not a Smart Card QR package")
        pkg = db.execute(
            select(SmartCardPackage).where(SmartCardPackage.plan_id == plan.id)
        ).scalar_one_or_none()
        if pkg is None or not pkg.is_active:
            raise SmartCardBillingError("Smart Card QR package is not available")
        return plan, pkg

    @staticmethod
    def start_seat_checkout(
        db: Session,
        *,
        org: Organisation,
        plan_id: str,
        seat_quantity: int,
        user_email: str = "",
        provider: str | None = None,
    ) -> dict[str, Any]:
        seats = int(seat_quantity or 0)
        if seats < 1:
            raise SmartCardBillingError("seat_quantity must be at least 1")
        if seats > 500:
            raise SmartCardBillingError("seat_quantity is too large")

        plan, _pkg = SmartCardBillingService._validate_plan(db, plan_id)
        # Smart Card is billed annually per seat
        currency, unit_minor, interval = PlanPriceService.billing_amount_for_org(
            db, org, plan, "yearly"
        )
        if unit_minor <= 0:
            raise SmartCardBillingError("Plan price is not configured for your billing currency.")
        amount_minor = int(unit_minor) * seats

        from app.services.payment_provider_router import PaymentProviderRouter

        prov = str(provider or "").strip().lower() or PaymentProviderRouter.primary_subscription_provider(
            db, org
        )
        if prov == "gocardless":
            # Seat qty uses card checkout; fall back to stripe/airwallex when GC is regional default
            from app.services.stripe_payment_service import StripePaymentService
            from app.services.airwallex_payment_service import AirwallexPaymentService

            if StripePaymentService.is_available(db):
                prov = "stripe"
            elif AirwallexPaymentService.is_available(db):
                prov = "airwallex"
            else:
                raise SmartCardBillingError(
                    "Smart Card seat checkout needs Stripe or Airwallex (card). Configure a card provider."
                )
        if prov not in {"stripe", "airwallex"}:
            raise SmartCardBillingError("provider must be stripe or airwallex")

        try:
            if prov == "airwallex":
                from app.services.airwallex_payment_service import AirwallexPaymentService

                if not AirwallexPaymentService.is_available(db):
                    raise SmartCardBillingError("Airwallex is not configured")
                intent = AirwallexPaymentService.create_subscription_checkout_intent(
                    db,
                    org,
                    amount_minor=amount_minor,
                    plan_id=plan.id,
                    billing_interval=interval or "yearly",
                    service_code=SMART_CARD_SERVICE_CODE,
                    customer_email=user_email,
                    seat_quantity=seats,
                )
            else:
                from app.services.stripe_payment_service import StripePaymentService

                if not StripePaymentService.is_available(db):
                    raise SmartCardBillingError("Stripe is not configured")
                intent = StripePaymentService.create_subscription_checkout_intent(
                    db,
                    org,
                    amount_minor=amount_minor,
                    plan_id=plan.id,
                    billing_interval=interval or "yearly",
                    service_code=SMART_CARD_SERVICE_CODE,
                    customer_email=user_email,
                    seat_quantity=seats,
                )
        except SmartCardBillingError:
            raise
        except Exception as exc:
            raise SmartCardBillingError(str(exc)) from exc

        return {
            "provider": prov,
            "currency": currency,
            "amount_minor": amount_minor,
            "unit_minor": unit_minor,
            "seat_quantity": seats,
            "billing_interval": interval or "yearly",
            "client_secret": intent.get("client_secret"),
            "intent_id": intent.get("payment_intent_id") or intent.get("intent_id"),
            "checkout": intent,
            "plan_id": plan.id,
            "service_code": SMART_CARD_SERVICE_CODE,
            "publishable_key": intent.get("publishable_key"),
        }

    @staticmethod
    def complete_seat_checkout(
        db: Session,
        *,
        org: Organisation,
        plan_id: str,
        provider: str,
        payment_intent_id: str,
        seat_quantity: int | None = None,
    ) -> Subscription:
        plan, _pkg = SmartCardBillingService._validate_plan(db, plan_id)
        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise SmartCardBillingError("payment_intent_id required")
        prov = str(provider or "").strip().lower()
        if prov not in {"stripe", "airwallex"}:
            raise SmartCardBillingError("provider must be stripe or airwallex")

        try:
            if prov == "stripe":
                from app.services.stripe_payment_service import StripePaymentService, StripeProviderError

                intent = StripePaymentService.retrieve_intent(db, pid)
            else:
                from app.services.airwallex_payment_service import AirwallexPaymentService, AirwallexProviderError

                intent = AirwallexPaymentService.retrieve_intent(db, pid)
        except Exception as exc:
            raise SmartCardBillingError(str(exc)) from exc

        status_raw = str(intent.get("status") or "")
        if prov == "airwallex":
            ok = status_raw.upper() == "SUCCEEDED" or status_raw.lower() in {"succeeded", "processing"}
        else:
            ok = status_raw.lower() in {"succeeded", "processing", "requires_capture"}
        if not ok:
            raise SmartCardBillingError("Payment not completed yet")

        meta = intent.get("metadata") or {}
        try:
            CardSubscriptionActivationService.verify_intent_metadata(
                meta, org_id=org.id, plan_id=plan.id
            )
        except CardSubscriptionActivationError as exc:
            raise SmartCardBillingError(str(exc)) from exc

        if str(meta.get("voxbulk_service_code") or "").strip() != SMART_CARD_SERVICE_CODE:
            raise SmartCardBillingError("Payment is not a Smart Card QR subscription checkout")

        seats = seat_quantity
        if seats is None:
            try:
                seats = int(meta.get("voxbulk_seat_quantity") or 0)
            except Exception:
                seats = 0
        if seats < 1:
            raise SmartCardBillingError("seat_quantity missing from payment")

        sub = CardSubscriptionActivationService.activate_from_payment(
            db,
            org=org,
            plan=plan,
            provider=prov,
            payment_intent_id=pid,
            billing_interval="yearly",
            service_code=SMART_CARD_SERVICE_CODE,
            seat_quantity=seats,
            amount_override_minor=int(meta.get("voxbulk_amount_minor") or 0) or None,
        )
        if prov == "stripe":
            from app.services.stripe_subscription_service import StripeSubscriptionService

            StripeSubscriptionService.sync_checkout_credentials(db, sub, payment_intent_id=pid)
        elif prov == "airwallex":
            from app.services.airwallex_subscription_service import AirwallexSubscriptionService

            AirwallexSubscriptionService.sync_checkout_credentials(db, sub, payment_intent_id=pid)
        return sub
