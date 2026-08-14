"""Activate core subscriptions from card checkout PaymentIntents (Stripe / Airwallex)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)

SUBSCRIPTION_CHECKOUT_KIND = "subscription_checkout"


class CardSubscriptionActivationError(ValueError):
    pass


class CardSubscriptionActivationService:
    @staticmethod
    def external_invoice_id(provider: str, payment_intent_id: str) -> str:
        prov = str(provider or "").strip().lower()
        pid = str(payment_intent_id or "").strip()
        return f"sub-card:{prov}:{pid}"

    @staticmethod
    def verify_intent_metadata(
        meta: dict[str, Any],
        *,
        org_id: str,
        plan_id: str | None = None,
    ) -> dict[str, str]:
        kind = str(meta.get("voxbulk_kind") or "").strip().lower()
        if kind != SUBSCRIPTION_CHECKOUT_KIND:
            raise CardSubscriptionActivationError("Payment is not a subscription checkout")
        meta_org = str(meta.get("voxbulk_org_id") or "").strip()
        if meta_org != str(org_id):
            raise CardSubscriptionActivationError("Payment does not belong to this organisation")
        meta_plan = str(meta.get("voxbulk_plan_id") or "").strip()
        if plan_id and meta_plan and meta_plan != str(plan_id):
            raise CardSubscriptionActivationError("Payment does not match the selected plan")
        if not meta_plan:
            raise CardSubscriptionActivationError("Payment is missing plan metadata")
        interval = PlanPriceService.normalize_billing_interval(meta.get("voxbulk_billing_interval"))
        service_code = str(meta.get("voxbulk_service_code") or "voxbulk").strip() or "voxbulk"
        return {
            "plan_id": meta_plan,
            "billing_interval": interval,
            "service_code": service_code,
        }

    @staticmethod
    def activate_from_payment(
        db: Session,
        *,
        org: Organisation,
        plan: Plan,
        provider: str,
        payment_intent_id: str,
        billing_interval: str | None = None,
        service_code: str | None = None,
        seat_quantity: int | None = None,
        amount_override_minor: int | None = None,
        trial_days: int = 0,
        catalog_amount_minor: int | None = None,
    ) -> Subscription:
        """Idempotent: upsert subscription, issue activation invoice, confirm first payment.

        When trial_days > 0, activates as status=trial with no charge invoice; amount_next_payment
        is the full catalog (seats × unit) for the first paid renewal.
        """
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        pid = str(payment_intent_id or "").strip()
        prov = str(provider or "").strip().lower()
        if not pid:
            raise CardSubscriptionActivationError("payment_intent_id required")
        if prov not in {"airwallex", "stripe"}:
            raise CardSubscriptionActivationError("provider must be airwallex or stripe")

        svc = str(service_code or "voxbulk").strip() or "voxbulk"
        interval = PlanPriceService.normalize_billing_interval(billing_interval)
        currency, amount_minor, resolved_interval = PlanPriceService.billing_amount_for_org(
            db, org, plan, interval
        )
        interval = resolved_interval or interval
        seats = int(seat_quantity or 0) if seat_quantity is not None else None
        if seats is not None and seats > 0 and amount_override_minor is None and svc == "smart_card":
            amount_minor = int(amount_minor or 0) * seats
        if amount_override_minor is not None and int(amount_override_minor) > 0:
            amount_minor = int(amount_override_minor)
        trial = max(0, int(trial_days or 0))
        catalog = (
            int(catalog_amount_minor)
            if catalog_amount_minor is not None and int(catalog_amount_minor) > 0
            else int(amount_minor or 0)
        )
        if trial > 0:
            # Trial: nothing due now; next invoice is full catalog.
            amount_minor = 0
        now = datetime.utcnow()
        period_days = trial if trial > 0 else (365 if interval == "yearly" else 30)

        sub = BillingAccessService.get_subscription(db, org.id, service_code=svc)
        if (
            sub is not None
            and str(sub.external_subscription_id or "") == pid
            and str(sub.status or "").lower() in {"active", "trial"}
        ):
            if seats is not None and seats > 0:
                sub.seat_quantity = seats
                db.add(sub)
                db.commit()
                db.refresh(sub)
            return sub

        if sub is None:
            sub = Subscription(org_id=org.id, plan_id=plan.id, service_code=svc, created_at=now)

        sub.plan_id = plan.id
        sub.status = "trial" if trial > 0 else "active"
        sub.payment_provider = prov
        sub.billing_currency = currency
        sub.billing_interval = interval
        sub.amount_next_payment_minor = catalog if trial > 0 else int(amount_minor or 0)
        sub.external_subscription_id = pid[:255]
        sub.current_period_end = now + timedelta(days=period_days)
        sub.next_billing_date = sub.current_period_end
        if seats is not None and seats > 0:
            sub.seat_quantity = seats
        if trial <= 0 and sub.first_payment_at is None:
            sub.first_payment_at = now
        sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        ext_inv = CardSubscriptionActivationService.external_invoice_id(prov, pid)
        # Always try to issue an invoice for paid activations (email resolved inside issue_from_payment).
        if amount_minor > 0 and trial <= 0:
            interval_label = "yearly" if interval == "yearly" else "monthly"
            qty = seats if seats and seats > 0 else 1
            unit = int(amount_minor // qty) if qty > 1 else int(amount_minor)
            try:
                InvoiceService.issue_from_payment(
                    db,
                    org_id=org.id,
                    client_email=email or "",
                    subtotal_pence=amount_minor,
                    currency=currency,
                    description=f"{plan.name} — subscription",
                    provider=prov,
                    external_invoice_id=ext_inv,
                    payment_reference=pid,
                    payment_method=prov,
                    status="paid",
                    line_items=[
                        {
                            "description": f"{plan.name} — {interval_label} subscription"
                            + (f" × {qty} seats" if qty > 1 else ""),
                            "quantity": qty,
                            "unit_pence": unit,
                            "total_pence": amount_minor,
                        }
                    ],
                    kind="subscription",
                )
            except Exception:
                logger.exception(
                    "card_subscription_activation_invoice_failed org_id=%s pi=%s",
                    org.id,
                    pid,
                )

        BillingAccessService.mark_first_payment_confirmed(db, org_id=org.id, sub=sub)
        if svc == "customer_feedback":
            from app.services.customer_feedback.billing_service import FeedbackBillingService

            FeedbackBillingService.on_subscription_activated(db, org_id=org.id, subscription=sub, plan=plan)
            FeedbackBillingService._tag_activation_invoice(db, org_id=org.id)
        elif svc == "smart_card":
            # Seat entitlement only — no usage wallet bootstrap
            pass
        else:
            UsageWalletService.bootstrap_from_plan(db, org_id=org.id, subscription=sub)
        db.refresh(sub)
        return sub

    @staticmethod
    def activate_from_webhook_intent(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        meta = intent.get("metadata") or {}
        parsed = CardSubscriptionActivationService.verify_intent_metadata(meta, org_id=org.id)
        plan = db.get(Plan, parsed["plan_id"])
        if plan is None:
            return {"ok": True, "ignored": True, "reason": "plan_not_found"}
        pid = str(intent.get("id") or "")
        seats = None
        try:
            raw_seats = meta.get("voxbulk_seat_quantity")
            if raw_seats is not None and str(raw_seats).strip():
                seats = int(raw_seats)
        except Exception:
            seats = None
        amount_override = None
        try:
            raw_amt = meta.get("voxbulk_amount_minor")
            if raw_amt is not None and str(raw_amt).strip():
                amount_override = int(raw_amt)
        except Exception:
            amount_override = None
        trial_days = 0
        try:
            raw_trial = meta.get("voxbulk_trial_days")
            if raw_trial is not None and str(raw_trial).strip():
                trial_days = max(0, int(raw_trial))
        except Exception:
            trial_days = 0
        catalog_amount = None
        try:
            raw_cat = meta.get("voxbulk_catalog_amount_minor")
            if raw_cat is not None and str(raw_cat).strip():
                catalog_amount = int(raw_cat)
        except Exception:
            catalog_amount = None
        sub = CardSubscriptionActivationService.activate_from_payment(
            db,
            org=org,
            plan=plan,
            provider=provider,
            payment_intent_id=pid,
            billing_interval=parsed["billing_interval"],
            service_code=parsed["service_code"],
            seat_quantity=seats,
            amount_override_minor=amount_override,
            trial_days=trial_days,
            catalog_amount_minor=catalog_amount,
        )
        return {"ok": True, "subscription_activated": True, "subscription_id": sub.id}
