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

# Product default: first month free, then pay per seat.
DEFAULT_SMART_CARD_TRIAL_DAYS = 30


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
    def resolve_trial_days(db: Session, *, org_id: str, plan: Plan) -> int:
        """Promo trial_days pending, else plan default, else product default (30)."""
        peeked = PromoDiscountService.peek_amount(
            db, org_id=org_id, service_kind=SMART_CARD_SERVICE_CODE, amount_minor=1
        )
        promo_trial = int(peeked.get("trial_days") or 0)
        if promo_trial > 0:
            return promo_trial
        plan_default = int(getattr(plan, "trial_days_default", 0) or 0)
        if plan_default > 0:
            return plan_default
        return DEFAULT_SMART_CARD_TRIAL_DAYS

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
    def _catalog_amount(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        seats: int,
        billing_interval: str,
    ) -> tuple[str, int, int, str]:
        currency, unit_minor, interval = PlanPriceService.billing_amount_for_org(
            db, org, plan, billing_interval
        )
        if unit_minor <= 0:
            raise SmartCardBillingError("Plan price is not configured for your billing currency.")
        amount_minor = int(unit_minor) * seats
        return currency, unit_minor, amount_minor, interval or "monthly"

    @staticmethod
    def _priced_amount(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        seats: int,
        billing_interval: str,
        apply_promo: bool,
    ) -> tuple[str, int, int, str, bool, int]:
        currency, unit_minor, amount_minor, interval = SmartCardBillingService._catalog_amount(
            db, org=org, plan=plan, seats=seats, billing_interval=billing_interval
        )
        promo_applied = False
        trial_days = 0
        if apply_promo:
            discounted = PromoDiscountService.apply_and_consume(
                db, org_id=org.id, service_kind=SMART_CARD_SERVICE_CODE, amount_minor=amount_minor
            )
            amount_minor = int(discounted["amount_minor"])
            promo_applied = bool(discounted.get("discount_applied"))
            trial_days = int(discounted.get("trial_days") or 0)
        return currency, unit_minor, amount_minor, interval, promo_applied, trial_days

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
        trial_days = SmartCardBillingService.resolve_trial_days(db, org_id=org_id, plan=plan)
        return {**res, "trial_days": trial_days}

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

        currency, unit_minor, catalog_minor, resolved_interval = SmartCardBillingService._catalog_amount(
            db, org=org, plan=plan, seats=seats, billing_interval=interval
        )
        trial_days = SmartCardBillingService.resolve_trial_days(db, org_id=org.id, plan=plan)

        # Percent/fixed promo without trial — peek then apply when charging now.
        peeked = PromoDiscountService.peek_amount(
            db, org_id=org.id, service_kind=SMART_CARD_SERVICE_CODE, amount_minor=catalog_minor
        )
        promo_trial = int(peeked.get("trial_days") or 0)
        if promo_trial > 0:
            trial_days = promo_trial

        try:
            prov = SmartCardBillingService._resolve_card_provider(db, org=org, preferred=preferred)
        except SmartCardBillingError:
            raise
        except Exception as exc:
            raise SmartCardBillingError(str(exc)) from exc

        # Free trial: collect card (SetupIntent / zero-amount consent), charge later.
        if trial_days > 0:
            # Consume pending trial promo so it cannot be reused.
            if peeked.get("discount_applied") and int(peeked.get("trial_days") or 0) > 0:
                PromoDiscountService.apply_and_consume(
                    db, org_id=org.id, service_kind=SMART_CARD_SERVICE_CODE, amount_minor=catalog_minor
                )
            try:
                if prov == "airwallex":
                    from app.services.airwallex_payment_service import AirwallexPaymentService

                    if not AirwallexPaymentService.is_available(db):
                        raise SmartCardBillingError("Airwallex is not configured")
                    intent = AirwallexPaymentService.create_subscription_setup_intent(
                        db,
                        org,
                        plan_id=plan.id,
                        billing_interval=resolved_interval,
                        service_code=SMART_CARD_SERVICE_CODE,
                        customer_email=user_email,
                        seat_quantity=seats,
                        trial_days=trial_days,
                        catalog_amount_minor=catalog_minor,
                    )
                else:
                    from app.services.stripe_payment_service import StripePaymentService

                    if not StripePaymentService.is_available(db):
                        raise SmartCardBillingError("Stripe is not configured")
                    intent = StripePaymentService.create_subscription_setup_intent(
                        db,
                        org,
                        plan_id=plan.id,
                        billing_interval=resolved_interval,
                        service_code=SMART_CARD_SERVICE_CODE,
                        customer_email=user_email,
                        seat_quantity=seats,
                        trial_days=trial_days,
                        catalog_amount_minor=catalog_minor,
                    )
            except SmartCardBillingError:
                raise
            except Exception as exc:
                raise SmartCardBillingError(str(exc)) from exc

            intent_id = (
                intent.get("setup_intent_id")
                or intent.get("payment_intent_id")
                or intent.get("intent_id")
                or ""
            )
            return {
                "provider": prov,
                "currency": currency,
                "amount_minor": 0,
                "unit_minor": unit_minor,
                "seat_quantity": seats,
                "billing_interval": resolved_interval,
                "client_secret": intent.get("client_secret"),
                "intent_id": intent_id,
                "payment_intent_id": intent_id,
                "setup_intent_id": intent.get("setup_intent_id") or intent_id,
                "checkout": intent,
                "plan_id": plan.id,
                "service_code": SMART_CARD_SERVICE_CODE,
                "publishable_key": intent.get("publishable_key"),
                "promo_discount_applied": bool(peeked.get("discount_applied")),
                "trial_days": trial_days,
                "mode": "setup",
                "after_trial_amount_minor": catalog_minor,
                "catalog_amount_minor": catalog_minor,
            }

        # Paid checkout (no trial): apply percent/fixed promo and charge now.
        currency, unit_minor, amount_minor, resolved_interval, promo_applied, _ = (
            SmartCardBillingService._priced_amount(
                db,
                org=org,
                plan=plan,
                seats=seats,
                billing_interval=interval,
                apply_promo=True,
            )
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
                catalog_amount_minor=catalog_minor,
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
                "trial_days": 0,
            }

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
            "trial_days": 0,
            "mode": "payment",
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

        is_setup = pid.startswith("seti_") or False
        try:
            if prov == "stripe":
                from app.services.stripe_payment_service import StripePaymentService

                if is_setup or pid.startswith("seti_"):
                    is_setup = True
                    intent = StripePaymentService.retrieve_setup_intent(db, pid)
                else:
                    intent = StripePaymentService.retrieve_intent(db, pid)
            else:
                from app.services.airwallex_payment_service import AirwallexPaymentService

                intent = AirwallexPaymentService.retrieve_intent(db, pid)
                meta_preview = intent.get("metadata") or {}
                if int(meta_preview.get("voxbulk_trial_days") or 0) > 0 and int(
                    meta_preview.get("voxbulk_amount_minor") or -1
                ) == 0:
                    is_setup = True
        except Exception as exc:
            raise SmartCardBillingError(str(exc)) from exc

        status_raw = str(intent.get("status") or "")
        if prov == "airwallex":
            ok = status_raw.upper() == "SUCCEEDED" or status_raw.lower() in {
                "succeeded",
                "processing",
                "requires_capture",
            }
            # Zero-amount / consent setup may land in REQUIRES_CUSTOMER_ACTION until confirmed via HPP.
            if is_setup and status_raw.upper() in {"SUCCEEDED", "PENDING", "REQUIRES_CAPTURE"}:
                ok = True
        elif is_setup:
            ok = status_raw.lower() in {"succeeded", "processing"}
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
        try:
            trial_days = max(0, int(meta.get("voxbulk_trial_days") or 0))
        except Exception:
            trial_days = 0
        try:
            catalog_amount = int(meta.get("voxbulk_catalog_amount_minor") or 0) or None
        except Exception:
            catalog_amount = None

        amount_override = None
        if not is_setup and not trial_days:
            try:
                amount_override = int(meta.get("voxbulk_amount_minor") or 0) or None
            except Exception:
                amount_override = None

        sub = CardSubscriptionActivationService.activate_from_payment(
            db,
            org=org,
            plan=plan,
            provider=prov,
            payment_intent_id=pid,
            billing_interval=interval,
            service_code=SMART_CARD_SERVICE_CODE,
            seat_quantity=seats,
            amount_override_minor=amount_override,
            trial_days=trial_days,
            catalog_amount_minor=catalog_amount,
        )
        if prov == "stripe":
            from app.services.stripe_subscription_service import StripeSubscriptionService

            StripeSubscriptionService.sync_checkout_credentials(db, sub, payment_intent_id=pid)
        elif prov == "airwallex":
            from app.services.airwallex_subscription_service import AirwallexSubscriptionService

            AirwallexSubscriptionService.sync_checkout_credentials(db, sub, payment_intent_id=pid)

        from app.services.billing_finance_service import BillingFinanceService

        BillingFinanceService.sync_subscription_billing_fields(db, sub)
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def promote_free_seats_if_due(db: Session, sub: Subscription, *, commit: bool = False) -> bool:
        """If added-seats free window ended, make all entitled seats billable."""
        free_until = getattr(sub, "added_seats_free_until", None)
        if free_until is None:
            return False
        from datetime import datetime

        now = datetime.utcnow()
        if free_until > now:
            return False
        entitled = max(0, int(getattr(sub, "seat_quantity", None) or 0))
        sub.billable_seat_quantity = entitled
        sub.added_seats_free_until = None
        sub.updated_at = now
        db.add(sub)
        if commit:
            db.commit()
            db.refresh(sub)
        else:
            db.flush()
        return True

    @staticmethod
    def effective_billable_seats(sub: Subscription) -> int:
        status = str(sub.status or "").lower()
        if status in {"trial", "trialing"}:
            return 0
        billable = getattr(sub, "billable_seat_quantity", None)
        if billable is not None:
            return max(0, int(billable))
        return max(0, int(getattr(sub, "seat_quantity", None) or 0))

    @staticmethod
    def seats_payload(db: Session, org_id: str) -> dict[str, Any]:
        from app.services.billing_access_service import BillingAccessService
        from app.services.billing_finance_service import BillingFinanceService
        from app.services.smart_card.company_service import SmartCardEntitlementService

        org = db.get(Organisation, org_id)
        if org is None:
            raise SmartCardBillingError("Organisation not found")
        sub = BillingAccessService.get_subscription(db, org_id, service_code=SMART_CARD_SERVICE_CODE)
        if sub is None or str(sub.status or "").lower() not in {"active", "trial", "trialing", "past_due"}:
            raise SmartCardBillingError("No active Smart Card subscription")
        SmartCardBillingService.promote_free_seats_if_due(db, sub, commit=True)
        plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
        seats = int(sub.seat_quantity or 0)
        billable = SmartCardBillingService.effective_billable_seats(sub)
        free_seats = max(0, seats - billable)
        active_reps = SmartCardEntitlementService.active_rep_count(db, org_id)
        unit_minor = 0
        currency = str(sub.billing_currency or org.billing_currency or "GBP")
        if plan is not None:
            currency, unit_minor, _ = PlanPriceService.billing_amount_for_org(
                db, org, plan, sub.billing_interval
            )
        next_minor = int(unit_minor or 0) * billable
        # After trial, next invoice is full catalog even if billable is 0 during trial.
        status = str(sub.status or "").lower()
        is_trial = status in {"trial", "trialing"}
        if is_trial:
            next_minor = int(unit_minor or 0) * max(seats, 1)
        finance = BillingFinanceService.subscription_finance_dict(db, sub, org=org, plan=plan)
        free_until = getattr(sub, "added_seats_free_until", None)
        trial_start = getattr(sub, "created_at", None)
        trial_end = sub.current_period_end if is_trial else None
        return {
            "seat_quantity": seats,
            "billable_seat_quantity": billable,
            "free_seat_quantity": free_seats,
            "added_seats_free_until": free_until.isoformat() if free_until else None,
            "trial_started_at": trial_start.isoformat() if trial_start else None,
            "trial_ends_at": trial_end.isoformat() if trial_end else None,
            "active_representatives": active_reps,
            "min_seats": max(1, active_reps),
            "max_seats": 500,
            "unit_price_minor": int(unit_minor or 0),
            "currency": currency,
            "estimated_next_amount_minor": next_minor,
            "next_billing_date": (
                sub.next_billing_date.isoformat()
                if sub.next_billing_date
                else (sub.current_period_end.isoformat() if sub.current_period_end else None)
            ),
            "status": status,
            "is_trial": is_trial,
            "billing_interval": getattr(sub, "billing_interval", None),
            "plan_id": sub.plan_id,
            "plan_name": plan.name if plan else None,
            "finance": finance or None,
        }

    @staticmethod
    def update_seats(db: Session, *, org_id: str, seat_quantity: int) -> dict[str, Any]:
        """Change seat count — next invoice only. New seats get 30 days free (option A)."""
        from datetime import datetime, timedelta

        from app.services.billing_access_service import BillingAccessService
        from app.services.billing_finance_service import BillingFinanceService
        from app.services.smart_card.company_service import SmartCardEntitlementService

        org = db.get(Organisation, org_id)
        if org is None:
            raise SmartCardBillingError("Organisation not found")
        seats = SmartCardBillingService._normalize_seats(seat_quantity)
        sub = BillingAccessService.get_subscription(db, org_id, service_code=SMART_CARD_SERVICE_CODE)
        if sub is None or str(sub.status or "").lower() not in {"active", "trial", "trialing", "past_due"}:
            raise SmartCardBillingError("No active Smart Card subscription")
        if bool(getattr(sub, "cancel_at_period_end", False)):
            raise SmartCardBillingError("Cannot change seats while cancellation is scheduled")
        SmartCardBillingService.promote_free_seats_if_due(db, sub, commit=False)
        active_reps = SmartCardEntitlementService.active_rep_count(db, org_id)
        if seats < active_reps:
            raise SmartCardBillingError(
                f"Cannot reduce below {active_reps} active representative(s). "
                "Deactivate representatives first, then reduce seats."
            )
        plan = db.get(Plan, sub.plan_id)
        if plan is None:
            raise SmartCardBillingError("Subscription plan not found")

        old_seats = max(0, int(sub.seat_quantity or 0))
        if seats == old_seats:
            return SmartCardBillingService.seats_payload(db, org_id)

        status = str(sub.status or "").lower()
        is_trial = status in {"trial", "trialing"}
        now = datetime.utcnow()

        if is_trial:
            # Whole-sub trial: all seats free until trial ends; then all become billable.
            sub.seat_quantity = seats
            sub.billable_seat_quantity = 0
            sub.added_seats_free_until = None
            _currency, unit_minor, catalog_minor, _interval = SmartCardBillingService._catalog_amount(
                db,
                org=org,
                plan=plan,
                seats=seats,
                billing_interval=str(sub.billing_interval or "monthly"),
            )
            sub.amount_next_payment_minor = catalog_minor
        elif seats > old_seats:
            # Option A: new seats free 30 days; keep current billable count.
            prev_billable = SmartCardBillingService.effective_billable_seats(sub)
            if prev_billable <= 0 and old_seats > 0:
                prev_billable = old_seats
            sub.seat_quantity = seats
            sub.billable_seat_quantity = prev_billable
            existing_free = getattr(sub, "added_seats_free_until", None)
            free_until = now + timedelta(days=DEFAULT_SMART_CARD_TRIAL_DAYS)
            if existing_free is not None and existing_free > free_until:
                free_until = existing_free
            sub.added_seats_free_until = free_until
            _currency, unit_minor, _catalog, _interval = SmartCardBillingService._catalog_amount(
                db,
                org=org,
                plan=plan,
                seats=max(prev_billable, 1) if prev_billable > 0 else 1,
                billing_interval=str(sub.billing_interval or "monthly"),
            )
            sub.amount_next_payment_minor = int(unit_minor or 0) * prev_billable
        else:
            # Downgrade: clamp billable to new entitlement.
            sub.seat_quantity = seats
            prev_billable = SmartCardBillingService.effective_billable_seats(sub)
            new_billable = min(prev_billable, seats)
            sub.billable_seat_quantity = new_billable
            if new_billable >= seats:
                sub.added_seats_free_until = None
            _currency, unit_minor, catalog_minor, _interval = SmartCardBillingService._catalog_amount(
                db,
                org=org,
                plan=plan,
                seats=max(new_billable, 1) if new_billable > 0 else seats,
                billing_interval=str(sub.billing_interval or "monthly"),
            )
            sub.amount_next_payment_minor = int(unit_minor or 0) * new_billable

        BillingFinanceService.sync_subscription_billing_fields(db, sub, commit=False)
        # Re-apply amount after sync in case sync recomputed from billable incorrectly during free window.
        if not is_trial:
            currency, amount = PlanPriceService.subscription_charge_amount_for_org(db, org, plan, sub)
            sub.billing_currency = currency
            sub.amount_next_payment_minor = amount
        sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return SmartCardBillingService.seats_payload(db, org_id)

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
