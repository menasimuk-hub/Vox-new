"""One-off Stripe / Airwallex checkout for Expo booth packages (pay before go-live)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoPackage
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.expo.booth_service import (
    EXPO_PACKAGE_CHECKOUT_KIND,
    ExpoBoothService,
    booth_is_paid,
)
from app.services.expo.expo_signup_trial_service import (
    PAYMENT_PROVIDER as SIGNUP_TRIAL_PROVIDER,
    ExpoSignupTrialService,
)

logger = logging.getLogger(__name__)


class ExpoBoothPaymentError(ValueError):
    pass


class ExpoBoothPaymentService:
    @staticmethod
    def package_price_minor(db: Session, booth: ExpoBooth, *, currency: str) -> int:
        if not booth.package_id:
            raise ExpoBoothPaymentError("This booth has no package selected")
        pkg = db.get(ExpoPackage, booth.package_id)
        if pkg is None or not pkg.plan_id:
            raise ExpoBoothPaymentError("Expo package pricing is not configured")
        plan = db.get(Plan, pkg.plan_id)
        if plan is None:
            raise ExpoBoothPaymentError("Expo package plan is missing")
        want = str(currency or "GBP").upper()
        price = db.execute(
            select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == want)
        ).scalar_one_or_none()
        if price is None:
            price = db.execute(select(PlanPrice).where(PlanPrice.plan_id == plan.id).limit(1)).scalar_one_or_none()
        if price and price.monthly_price_minor is not None:
            return int(price.monthly_price_minor)
        return int(plan.price_gbp_pence or 0)

    @staticmethod
    def effective_amount_minor(db: Session, *, org: Organisation, booth: ExpoBooth, currency: str) -> int:
        """Catalog price, or 0 when a silent signup trial covers this booth."""
        if ExpoSignupTrialService.has_usable_trial(db, org_id=org.id, booth=booth):
            return 0
        return ExpoBoothPaymentService.package_price_minor(db, booth, currency=currency)

    @staticmethod
    def pay_options(db: Session, *, org: Organisation, booth: ExpoBooth) -> dict[str, Any]:
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.stripe_payment_service import StripePaymentService

        currency = resolve_org_currency(db, org, persist=True)
        amount = ExpoBoothPaymentService.effective_amount_minor(db, org=org, booth=booth, currency=currency)
        providers = []
        if amount > 0 and StripePaymentService.is_available(db):
            providers.append(
                {
                    "id": "stripe",
                    "label": "Card (Stripe)",
                    "publishable_key": StripePaymentService.publishable_key(db),
                }
            )
        if amount > 0 and AirwallexPaymentService.is_available(db):
            providers.append({"id": "airwallex", "label": "Card (Airwallex)"})
        return {
            "ok": True,
            "booth_id": booth.id,
            "payment_status": str(getattr(booth, "payment_status", None) or "unpaid"),
            "is_paid": booth_is_paid(booth),
            "amount_minor": amount,
            "amount_display": money_display(amount, currency),
            "currency": currency,
            "providers": providers,
            "booth": ExpoBoothService.serialize_booth(db, booth),
        }

    @staticmethod
    def create_intent(
        db: Session,
        *,
        org: Organisation,
        booth: ExpoBooth,
        provider: str,
    ) -> dict[str, Any]:
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.stripe_payment_service import StripePaymentService

        if booth_is_paid(booth):
            raise ExpoBoothPaymentError("This booth is already paid")
        if org.id != booth.org_id:
            raise ExpoBoothPaymentError("Booth does not belong to this organisation")
        currency = resolve_org_currency(db, org, persist=True)
        trial_covers = ExpoSignupTrialService.has_usable_trial(db, org_id=org.id, booth=booth)
        amount = 0 if trial_covers else ExpoBoothPaymentService.package_price_minor(db, booth, currency=currency)
        if amount <= 0:
            provider_label = SIGNUP_TRIAL_PROVIDER if trial_covers else "free"
            intent_prefix = "trial" if trial_covers else "free"
            if trial_covers:
                ExpoSignupTrialService.consume_for_booth(db, org_id=org.id, booth=booth)
            ExpoBoothPaymentService.mark_paid(
                db,
                booth=booth,
                provider=provider_label,
                payment_intent_id=f"{intent_prefix}-{booth.id[:8]}",
            )
            return {
                "ok": True,
                "provider": provider_label,
                "paid": True,
                "amount_minor": 0,
                "currency": currency,
                "booth": ExpoBoothService.serialize_booth(db, booth),
            }

        prov = str(provider or "").strip().lower()
        meta = {
            "voxbulk_booth_id": booth.id,
            "voxbulk_package_id": str(booth.package_id or ""),
        }
        if prov == "stripe":
            payload = StripePaymentService._create_payment_intent(
                db,
                org,
                amount_minor=amount,
                kind=EXPO_PACKAGE_CHECKOUT_KIND,
                description=f"Expo package — {booth.company_display_name}"[:255],
                metadata_extra=meta,
            )
        elif prov == "airwallex":
            request_id = str(uuid.uuid4())
            intent = AirwallexPaymentService._request(
                db,
                "POST",
                "/api/v1/pa/payment_intents/create",
                payload={
                    "request_id": request_id,
                    "amount": round(int(amount) / 100.0, 2),
                    "currency": currency,
                    "merchant_order_id": f"voxbulk-expo-{booth.id[:8]}-{int(time.time())}",
                    "metadata": {
                        "voxbulk_org_id": org.id,
                        "voxbulk_kind": EXPO_PACKAGE_CHECKOUT_KIND,
                        **meta,
                    },
                    "descriptor": "VoxBulk Expo package"[:22],
                },
            )
            payload = {
                "provider": "airwallex",
                "payment_intent_id": str(intent.get("id") or ""),
                "client_secret": str(intent.get("client_secret") or ""),
                "amount_minor": int(amount),
                "currency": currency,
                "status": str(intent.get("status") or ""),
                "environment": str(AirwallexPaymentService.get_config(db).get("environment") or "demo"),
            }
        else:
            raise ExpoBoothPaymentError("provider must be stripe or airwallex")

        booth.payment_status = "pending"
        booth.payment_provider = prov
        booth.payment_intent_id = str(payload.get("payment_intent_id") or "")[:128] or None
        booth.updated_at = datetime.utcnow()
        db.add(booth)
        db.commit()
        db.refresh(booth)
        return {"ok": True, **payload, "booth_id": booth.id}

    @staticmethod
    def mark_paid(
        db: Session,
        *,
        booth: ExpoBooth,
        provider: str,
        payment_intent_id: str,
    ) -> dict[str, Any]:
        if booth_is_paid(booth):
            return {
                "ok": True,
                "paid": True,
                "duplicate": True,
                "booth": ExpoBoothService.serialize_booth(db, booth),
            }
        now = datetime.utcnow()
        booth.payment_status = "paid"
        booth.paid_at = now
        booth.payment_provider = str(provider or "")[:32] or None
        booth.payment_intent_id = str(payment_intent_id or "")[:128] or booth.payment_intent_id
        booth.updated_at = now
        db.add(booth)
        db.commit()
        db.refresh(booth)
        logger.info(
            "expo_booth_paid booth_id=%s provider=%s intent=%s",
            booth.id,
            provider,
            payment_intent_id,
        )
        return {
            "ok": True,
            "paid": True,
            "duplicate": False,
            "booth": ExpoBoothService.serialize_booth(db, booth),
        }

    @staticmethod
    def confirm(
        db: Session,
        *,
        org: Organisation,
        booth: ExpoBooth,
        provider: str,
        payment_intent_id: str,
    ) -> dict[str, Any]:
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.stripe_payment_service import StripePaymentService

        if booth_is_paid(booth):
            return {
                "ok": True,
                "paid": True,
                "duplicate": True,
                "booth": ExpoBoothService.serialize_booth(db, booth),
            }
        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise ExpoBoothPaymentError("payment_intent_id required")
        prov = str(provider or "").strip().lower()

        if prov == "stripe":
            intent = StripePaymentService.retrieve_intent(db, pid)
            meta = intent.get("metadata") or {}
            if str(meta.get("voxbulk_org_id") or "") != org.id:
                raise ExpoBoothPaymentError("Payment does not belong to this organisation")
            if str(meta.get("voxbulk_kind") or "") != EXPO_PACKAGE_CHECKOUT_KIND:
                raise ExpoBoothPaymentError("Payment is not for an Expo package")
            if str(meta.get("voxbulk_booth_id") or "") != booth.id:
                raise ExpoBoothPaymentError("Payment does not match this booth")
            if str(intent.get("status") or "") != "succeeded":
                return {"ok": False, "paid": False, "status": intent.get("status")}
            return ExpoBoothPaymentService.mark_paid(
                db, booth=booth, provider="stripe", payment_intent_id=pid
            )

        if prov == "airwallex":
            intent = AirwallexPaymentService.retrieve_intent(db, pid)
            meta = intent.get("metadata") or {}
            if str(meta.get("voxbulk_org_id") or "") != org.id:
                raise ExpoBoothPaymentError("Payment does not belong to this organisation")
            if str(meta.get("voxbulk_kind") or "") != EXPO_PACKAGE_CHECKOUT_KIND:
                raise ExpoBoothPaymentError("Payment is not for an Expo package")
            if str(meta.get("voxbulk_booth_id") or "") != booth.id:
                raise ExpoBoothPaymentError("Payment does not match this booth")
            status = str(intent.get("status") or "").upper()
            if status != "SUCCEEDED":
                return {"ok": False, "paid": False, "status": status}
            return ExpoBoothPaymentService.mark_paid(
                db, booth=booth, provider="airwallex", payment_intent_id=pid
            )

        raise ExpoBoothPaymentError("provider must be stripe or airwallex")

    @staticmethod
    def mark_paid_from_webhook(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        meta = intent.get("metadata") or {}
        booth_id = str(meta.get("voxbulk_booth_id") or "").strip()
        pid = str(intent.get("id") or "")
        if not booth_id:
            return {"ok": True, "ignored": True, "reason": "missing_booth"}
        booth = db.get(ExpoBooth, booth_id)
        if booth is None or booth.org_id != org.id:
            return {"ok": True, "ignored": True, "reason": "booth_not_found"}
        return ExpoBoothPaymentService.mark_paid(
            db, booth=booth, provider=provider, payment_intent_id=pid
        )
