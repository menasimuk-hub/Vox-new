"""Stripe customer vaulting and off-session subscription renewals."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.plan_price_service import PlanPriceService
from app.services.stripe_payment_service import StripePaymentService, StripeProviderError

logger = logging.getLogger(__name__)

SUBSCRIPTION_RENEWAL_KIND = "subscription_renewal"


class StripeBillingError(ValueError):
    pass


class StripeBillingService:
    @staticmethod
    def ensure_customer(db: Session, org: Organisation, *, email: str) -> str:
        from app.services.billing_access_service import BillingAccessService

        sub = BillingAccessService.get_subscription(db, org.id)
        if sub and str(sub.external_customer_id or "").strip():
            return str(sub.external_customer_id)

        data: dict[str, Any] = {
            "email": str(email or org.contact_email or "").strip() or f"billing+{org.id[:8]}@voxbulk.local",
            "name": str(org.name or "")[:255] or None,
            "metadata[org_id]": org.id,
        }
        data = {k: v for k, v in data.items() if v is not None}
        customer = StripePaymentService._request(db, "POST", "/customers", data=data)
        customer_id = str(customer.get("id") or "").strip()
        if not customer_id:
            raise StripeBillingError("Stripe did not return a customer id")
        return customer_id

    @staticmethod
    def subscription_checkout_data(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        plan_id: str,
        billing_interval: str,
        service_code: str,
        customer_email: str,
    ) -> dict[str, Any]:
        from app.services.billing_currency import resolve_org_currency

        customer_id = StripeBillingService.ensure_customer(db, org, email=customer_email)
        currency = resolve_org_currency(db, org, persist=True)
        data: dict[str, Any] = {
            "amount": int(amount_minor),
            "currency": currency.lower(),
            "customer": customer_id,
            "setup_future_usage": "off_session",
            "automatic_payment_methods[enabled]": "true",
            "metadata[voxbulk_org_id]": org.id,
            "metadata[voxbulk_kind]": "subscription_checkout",
            "metadata[voxbulk_plan_id]": plan_id,
            "metadata[voxbulk_billing_interval]": billing_interval,
            "metadata[voxbulk_service_code]": service_code,
            "description": f"VoxBulk subscription — {org.name}"[:255],
        }
        return data

    @staticmethod
    def parse_intent_credentials(intent: dict[str, Any]) -> dict[str, str | None]:
        customer_raw = intent.get("customer")
        if isinstance(customer_raw, dict):
            customer_id = str(customer_raw.get("id") or "").strip() or None
        else:
            customer_id = str(customer_raw or "").strip() or None

        pm_raw = intent.get("payment_method")
        if isinstance(pm_raw, dict):
            payment_method_id = str(pm_raw.get("id") or "").strip() or None
        else:
            payment_method_id = str(pm_raw or "").strip() or None

        return {
            "customer_id": customer_id,
            "payment_method_id": payment_method_id,
        }

    @staticmethod
    def sync_credentials_from_intent(db: Session, sub: Subscription, *, payment_intent_id: str) -> Subscription:
        intent = StripePaymentService.retrieve_intent(db, payment_intent_id)
        creds = StripeBillingService.parse_intent_credentials(intent)
        if creds.get("customer_id"):
            sub.external_customer_id = str(creds["customer_id"])
        if creds.get("payment_method_id"):
            sub.external_subscription_id = str(creds["payment_method_id"])
            sub.mandate_status = "verified"
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def is_managed_subscription(sub: Subscription | None) -> bool:
        if sub is None or str(sub.payment_provider or "").lower() != "stripe":
            return False
        return bool(
            str(sub.external_customer_id or "").strip()
            and str(sub.external_subscription_id or "").strip()
        )

    @staticmethod
    def charge_renewal(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan,
        amount_minor: int,
        currency: str,
        period_key: str,
    ) -> dict[str, Any]:
        customer_id = str(sub.external_customer_id or "").strip()
        payment_method_id = str(sub.external_subscription_id or "").strip()
        if not customer_id or not payment_method_id:
            raise StripeBillingError("Stripe saved payment method is missing — customer must re-subscribe")

        return StripeBillingService.charge_managed_payment(
            db,
            org=org,
            sub=sub,
            plan=plan,
            amount_minor=amount_minor,
            currency=currency,
            payment_kind=SUBSCRIPTION_RENEWAL_KIND,
            reference_key=period_key,
            description=f"VoxBulk subscription renewal — {plan.name}",
            extra_metadata={"voxbulk_period_key": period_key},
        )

    @staticmethod
    def charge_managed_payment(
        db: Session,
        *,
        org: Organisation,
        sub: Subscription,
        plan: Plan,
        amount_minor: int,
        currency: str,
        payment_kind: str,
        reference_key: str,
        description: str,
        extra_metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        customer_id = str(sub.external_customer_id or "").strip()
        payment_method_id = str(sub.external_subscription_id or "").strip()
        if not customer_id or not payment_method_id:
            raise StripeBillingError("Stripe saved payment method is missing — customer must re-subscribe")

        data: dict[str, Any] = {
            "amount": int(amount_minor),
            "currency": currency.lower(),
            "customer": customer_id,
            "payment_method": payment_method_id,
            "off_session": "true",
            "confirm": "true",
            "metadata[voxbulk_org_id]": org.id,
            "metadata[voxbulk_kind]": payment_kind,
            "metadata[voxbulk_subscription_id]": sub.id,
            "metadata[voxbulk_plan_id]": plan.id,
            "metadata[voxbulk_reference_key]": reference_key,
            "description": description[:255],
        }
        for key, value in (extra_metadata or {}).items():
            data[f"metadata[{key}]"] = value

        intent = StripePaymentService._request(db, "POST", "/payment_intents", data=data)
        return {
            "payment_intent_id": str(intent.get("id") or ""),
            "status": str(intent.get("status") or "").lower(),
            "intent": intent,
        }

    @staticmethod
    def intent_amount_minor(intent: dict[str, Any]) -> int:
        return int(intent.get("amount_received") or intent.get("amount") or 0)

    @staticmethod
    def handle_renewal_payment_success(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.billing_access_service import BillingAccessService
        from app.services.billing_lifecycle_service import BillingLifecycleService
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        meta = intent.get("metadata") or {}
        sub_id = str(meta.get("voxbulk_subscription_id") or "").strip()
        period_key = str(meta.get("voxbulk_period_key") or "").strip()
        pid = str(intent.get("id") or "").strip()
        sub = db.get(Subscription, sub_id) if sub_id else BillingAccessService.get_subscription(db, org.id)
        if sub is None:
            return {"ok": True, "ignored": True, "reason": "subscription_not_found"}
        plan = db.get(Plan, sub.plan_id)
        if plan is None:
            return {"ok": True, "ignored": True, "reason": "plan_not_found"}

        amount_minor = StripeBillingService.intent_amount_minor(intent)
        currency = str(intent.get("currency") or sub.billing_currency or "gbp").upper()
        ext_inv = f"sub-renewal:{sub.id}:{period_key}" if period_key else f"sub-renewal:{sub.id}:{pid}"
        existing = InvoiceService.get_by_external(db, provider="stripe", external_invoice_id=ext_inv)
        if existing is not None and str(existing.status or "").lower() == "paid":
            return {"ok": True, "duplicate": True, "invoice_id": existing.id}

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        interval_label = "yearly" if str(sub.billing_interval or "") == "yearly" else "monthly"
        desc = f"{plan.name} — {interval_label} subscription renewal"
        if amount_minor <= 0:
            _currency, amount_minor, _ = PlanPriceService.billing_amount_for_org(
                db, org, plan, sub.billing_interval
            )

        if existing is None:
            invoice, _created, _emailed = InvoiceService.issue_from_payment(
                db,
                org_id=org.id,
                client_email=email or "billing@voxbulk.local",
                subtotal_pence=amount_minor,
                currency=currency,
                description=desc,
                provider="stripe",
                external_invoice_id=ext_inv,
                payment_reference=pid,
                payment_method="stripe",
                status="paid",
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
        else:
            invoice = existing
            invoice.status = "paid"
            invoice.dd_status = "confirmed"
            if pid:
                invoice.payment_reference = pid
            db.add(invoice)

        if period_key:
            from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService

            CardRenewalLifecycleService.mark_renewal_paid(
                db, sub=sub, provider="stripe", period_key=period_key
            )
        BillingLifecycleService._advance_subscription_period(db, sub, plan)
        return {"ok": True, "renewal_paid": True, "invoice_id": invoice.id, "subscription_id": sub.id}
