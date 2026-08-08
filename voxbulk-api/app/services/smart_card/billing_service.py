"""Smart Card QR seat billing — quantity × unit price (monthly/yearly GoCardless, card fallback)."""

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
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
from app.services.payment_provider_router import PaymentProviderRouter
from app.services.plan_price_service import PlanPriceService
from app.services.promo_discount_service import PromoDiscountService

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
    def _normalize_seats(seat_quantity: int) -> int:
        seats = int(seat_quantity or 0)
        if seats < 1:
            raise SmartCardBillingError("seat_quantity must be at least 1")
        if seats > 500:
            raise SmartCardBillingError("seat_quantity is too large")
        return seats

    @staticmethod
    def _resolve_card_provider(db: Session, *, org: Organisation, preferred: str | None = None) -> str:
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.stripe_payment_service import StripePaymentService

        prov = str(preferred or "").strip().lower()
        if prov == "stripe" and StripePaymentService.is_available(db):
            return "stripe"
        if prov == "airwallex" and AirwallexPaymentService.is_available(db):
            return "airwallex"
        primary = PaymentProviderRouter.primary_subscription_provider(db, org)
        if primary == "stripe" and StripePaymentService.is_available(db):
            return "stripe"
        if primary == "airwallex" and AirwallexPaymentService.is_available(db):
            return "airwallex"
        if StripePaymentService.is_available(db):
            return "stripe"
        if AirwallexPaymentService.is_available(db):
            return "airwallex"
        raise SmartCardBillingError(
            "Smart Card seat checkout needs Stripe or Airwallex (card). Configure a card provider."
        )

    @staticmethod
    def _priced_amount(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        seats: int,
        billing_interval: str,
        apply_promo: bool,
    ) -> tuple[str, int, int, str, bool]:
        currency, unit_minor, interval = PlanPriceService.billing_amount_for_org(
            db, org, plan, billing_interval
        )
        if unit_minor <= 0:
            raise SmartCardBillingError("Plan price is not configured for your billing currency.")
        amount_minor = int(unit_minor) * seats
        promo_applied = False
        if apply_promo:
            discounted = PromoDiscountService.apply_and_consume(
                db, org_id=org.id, service_kind=SMART_CARD_SERVICE_CODE, amount_minor=amount_minor
            )
            amount_minor = int(discounted["amount_minor"])
            promo_applied = bool(discounted.get("discount_applied"))
        return currency, unit_minor, amount_minor, interval or "monthly", promo_applied

    @staticmethod
    def start_gocardless_signup(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        plan_id: str,
        seat_quantity: int,
        billing_interval: str | None = None,
    ) -> dict[str, Any]:
        plan, _pkg = SmartCardBillingService._validate_plan(db, plan_id)
        seats = SmartCardBillingService._normalize_seats(seat_quantity)
        interval = PlanPriceService.normalize_billing_interval(billing_interval)
        if interval not in ("monthly", "yearly"):
            raise SmartCardBillingError("Choose monthly or yearly billing for GoCardless Smart Card seats.")
        try:
            res = BillingService.start_gocardless_redirect_flow(
                db,
                org_id=org_id,
                user_id=user_id,
                plan_id=plan.id,
                flow_purpose=SMART_CARD_SERVICE_CODE,
                billing_interval=interval,
                seat_quantity=seats,
            )
        except (GoCardlessConfigError, GoCardlessProviderError, ValueError) as exc:
            raise SmartCardBillingError(str(exc)) from exc
        return res

    @staticmethod
    def start_seat_checkout(
        db: Session,
        *,
        org: Organisation,
        plan_id: str,
        seat_quantity: int,
        user_email: str = "",
        provider: str | None = None,
        billing_interval: str | None = None,
    ) -> dict[str, Any]:
        seats = SmartCardBillingService._normalize_seats(seat_quantity)
        plan, _pkg = SmartCardBillingService._validate_plan(db, plan_id)
        interval = PlanPriceService.normalize_billing_interval(billing_interval or "yearly")

        from app.services.gocardless_service import BillingService as GcBilling

        preferred = str(provider or "").strip().lower() or None
        # Explicit card choice always wins — do not force Direct Debit when the user picked Stripe/Airwallex.
        if preferred in {"stripe", "airwallex"}:
            pass
        else:
            primary = preferred or PaymentProviderRouter.primary_subscription_provider(db, org)
            gc_opts = GcBilling.payment_options(db)
            if (
                interval in ("monthly", "yearly")
                and primary == "gocardless"
                and bool(gc_opts.get("gocardless_available"))
            ):
                raise SmartCardBillingError(
                    "Use Direct Debit checkout for GoCardless, or choose Card (Stripe)."
                )

        currency, unit_minor, amount_minor, resolved_interval, promo_applied = SmartCardBillingService._priced_amount(
            db,
            org=org,
            plan=plan,
            seats=seats,
            billing_interval=interval,
            apply_promo=True,
        )

        if amount_minor <= 0:
            try:
                stub_prov = SmartCardBillingService._resolve_card_provider(db, org=org, preferred=preferred)
            except SmartCardBillingError:
                stub_prov = "stripe"
            sub = CardSubscriptionActivationService.activate_from_payment(
                db,
                org=org,
                plan=plan,
                provider=stub_prov,
                payment_intent_id=f"promo-discount-sc-{org.id[:8]}-{seats}",
                billing_interval=resolved_interval,
                service_code=SMART_CARD_SERVICE_CODE,
                seat_quantity=seats,
                amount_override_minor=0,
            )
            return {
                "provider": "promo_discount",
                "paid": True,
                "currency": currency,
                "amount_minor": 0,
                "unit_minor": unit_minor,
                "seat_quantity": seats,
                "billing_interval": resolved_interval,
                "plan_id": plan.id,
                "service_code": SMART_CARD_SERVICE_CODE,
                "subscription_id": sub.id,
                "promo_discount_applied": True,
            }

        try:
            prov = SmartCardBillingService._resolve_card_provider(db, org=org, preferred=preferred)
        except SmartCardBillingError:
            raise
        except Exception as exc:
            raise SmartCardBillingError(str(exc)) from exc

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
                    billing_interval=resolved_interval,
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
                    billing_interval=resolved_interval,
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
            "billing_interval": resolved_interval,
            "client_secret": intent.get("client_secret"),
            "intent_id": intent.get("payment_intent_id") or intent.get("intent_id"),
            "checkout": intent,
            "plan_id": plan.id,
            "service_code": SMART_CARD_SERVICE_CODE,
            "publishable_key": intent.get("publishable_key"),
            "promo_discount_applied": promo_applied,
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
        billing_interval: str | None = None,
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
                from app.services.stripe_payment_service import StripePaymentService

                intent = StripePaymentService.retrieve_intent(db, pid)
            else:
                from app.services.airwallex_payment_service import AirwallexPaymentService

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

        interval = PlanPriceService.normalize_billing_interval(
            billing_interval
            or meta.get("voxbulk_billing_interval")
            or "yearly"
        )

        sub = CardSubscriptionActivationService.activate_from_payment(
            db,
            org=org,
            plan=plan,
            provider=prov,
            payment_intent_id=pid,
            billing_interval=interval,
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

    @staticmethod
    def cancellation_payload(db: Session, org_id: str) -> dict[str, Any]:
        from app.services.billing_access_service import BillingAccessService
        from app.services.subscription_cancellation_service import SubscriptionCancellationService

        org = db.get(Organisation, org_id)
        if org is None:
            raise SmartCardBillingError("Organisation not found")
        sub = BillingAccessService.get_subscription(db, org_id, service_code=SMART_CARD_SERVICE_CODE)
        plan = db.get(Plan, sub.plan_id) if sub else None
        refund_review = SubscriptionCancellationService.get_open_refund_review(db, org_id) if sub else None
        return SubscriptionCancellationService.cancellation_dict(db, org, sub, plan, refund_review=refund_review)

    @staticmethod
    def request_cancellation(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        reason: str | None = None,
        requested_refund_type: str = "none",
    ) -> dict[str, Any]:
        from app.services.subscription_cancellation_service import (
            SubscriptionCancellationError,
            SubscriptionCancellationService,
        )

        try:
            return SubscriptionCancellationService.request_cancellation(
                db,
                org_id=org_id,
                user_id=user_id,
                reason=reason,
                requested_refund_type=requested_refund_type,
                service_code=SMART_CARD_SERVICE_CODE,
            )
        except SubscriptionCancellationError as exc:
            raise SmartCardBillingError(str(exc)) from exc

    @staticmethod
    def reverse_cancellation(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        note: str | None = None,
    ) -> dict[str, Any]:
        from app.services.subscription_cancellation_service import (
            SubscriptionCancellationError,
            SubscriptionCancellationService,
        )

        try:
            return SubscriptionCancellationService.reverse_cancellation(
                db,
                org_id=org_id,
                admin_user_id=user_id,
                note=note or "Customer reversed scheduled cancellation",
                service_code=SMART_CARD_SERVICE_CODE,
            )
        except SubscriptionCancellationError as exc:
            raise SmartCardBillingError(str(exc)) from exc
