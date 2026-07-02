"""Airwallex customer vaulting and merchant-initiated subscription renewals."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.airwallex_payment_service import AirwallexPaymentService, AirwallexProviderError
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)

SUBSCRIPTION_RENEWAL_KIND = "subscription_renewal"


class AirwallexBillingError(ValueError):
    pass


class AirwallexBillingService:
    @staticmethod
    def ensure_customer(db: Session, org: Organisation, *, email: str) -> str:
        from app.services.billing_access_service import BillingAccessService

        sub = BillingAccessService.get_subscription(db, org.id)
        if sub and str(sub.external_customer_id or "").strip():
            return str(sub.external_customer_id)

        payload: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "merchant_customer_id": org.id,
            "email": str(email or org.contact_email or "").strip() or f"billing+{org.id[:8]}@voxbulk.local",
        }
        name = str(org.name or "").strip()
        if name:
            payload["first_name"] = name[:128]
        customer = AirwallexPaymentService._request(db, "POST", "/api/v1/pa/customers/create", payload=payload)
        customer_id = str(customer.get("id") or "").strip()
        if not customer_id:
            raise AirwallexBillingError("Airwallex did not return a customer id")
        return customer_id

    @staticmethod
    def subscription_checkout_payload(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        plan_id: str,
        billing_interval: str,
        service_code: str,
        customer_email: str,
    ) -> dict[str, Any]:
        customer_id = AirwallexBillingService.ensure_customer(db, org, email=customer_email)
        currency = org.billing_currency or "GBP"
        from app.services.billing_currency import resolve_org_currency

        currency = resolve_org_currency(db, org, persist=True)
        return {
            "request_id": str(uuid.uuid4()),
            "amount": round(int(amount_minor) / 100.0, 2),
            "currency": currency,
            "customer_id": customer_id,
            "merchant_order_id": f"voxbulk-sub-{org.id[:8]}-{int(time.time())}",
            "metadata": {
                "voxbulk_org_id": org.id,
                "voxbulk_kind": "subscription_checkout",
                "voxbulk_plan_id": plan_id,
                "voxbulk_billing_interval": billing_interval,
                "voxbulk_service_code": service_code,
            },
            "descriptor": "VoxBulk subscription",
            "payment_consent": {
                "next_triggered_by": "merchant",
                "merchant_trigger_reason": "scheduled",
            },
        }

    @staticmethod
    def parse_intent_credentials(intent: dict[str, Any]) -> dict[str, str | None]:
        latest = (intent.get("latest_payment_attempt") or {}) if isinstance(intent.get("latest_payment_attempt"), dict) else {}
        payment_method = latest.get("payment_method") if isinstance(latest.get("payment_method"), dict) else {}
        if not payment_method:
            root_pm = intent.get("payment_method")
            payment_method = root_pm if isinstance(root_pm, dict) else {}
        payment_method_id = str(payment_method.get("id") or "").strip() or None
        consent_id = str(intent.get("payment_consent_id") or "").strip() or None
        customer_id = str(intent.get("customer_id") or "").strip() or None
        consent_status = str(intent.get("payment_consent_status") or "").strip().lower() or None
        return {
            "customer_id": customer_id,
            "payment_consent_id": consent_id,
            "payment_method_id": payment_method_id,
            "consent_status": consent_status,
        }

    @staticmethod
    def sync_credentials_from_intent(db: Session, sub: Subscription, *, payment_intent_id: str) -> Subscription:
        intent = AirwallexPaymentService.retrieve_intent(db, payment_intent_id)
        creds = AirwallexBillingService.parse_intent_credentials(intent)
        if creds.get("customer_id"):
            sub.external_customer_id = str(creds["customer_id"])
        if creds.get("payment_consent_id"):
            sub.mandate_id = str(creds["payment_consent_id"])
            sub.mandate_status = str(creds.get("consent_status") or "verified")
        if creds.get("payment_method_id"):
            sub.external_subscription_id = str(creds["payment_method_id"])
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def is_managed_subscription(sub: Subscription | None) -> bool:
        if sub is None or str(sub.payment_provider or "").lower() != "airwallex":
            return False
        return bool(
            str(sub.external_customer_id or "").strip()
            and str(sub.mandate_id or "").strip()
            and str(sub.external_subscription_id or "").strip()
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
        consent_id = str(sub.mandate_id or "").strip()
        if not customer_id or not payment_method_id:
            raise AirwallexBillingError("Airwallex saved payment method is missing — customer must re-subscribe")

        metadata: dict[str, str] = {
            "voxbulk_org_id": org.id,
            "voxbulk_kind": payment_kind,
            "voxbulk_subscription_id": sub.id,
            "voxbulk_plan_id": plan.id,
            "voxbulk_reference_key": reference_key,
        }
        metadata.update(extra_metadata or {})

        create_payload: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "amount": round(int(amount_minor) / 100.0, 2),
            "currency": currency,
            "customer_id": customer_id,
            "merchant_order_id": f"voxbulk-{payment_kind[:12]}-{sub.id[:8]}-{reference_key[:24]}",
            "metadata": metadata,
            "descriptor": description[:32] or "VoxBulk subscription",
        }
        intent = AirwallexPaymentService._request(
            db, "POST", "/api/v1/pa/payment_intents/create", payload=create_payload
        )
        intent_id = str(intent.get("id") or "").strip()
        if not intent_id:
            raise AirwallexBillingError("Airwallex payment intent missing id")

        confirm_payload: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "payment_method": {"id": payment_method_id, "type": "card"},
            "triggered_by": "merchant",
            "merchant_trigger_reason": "scheduled",
        }
        if consent_id:
            confirm_payload["payment_consent_id"] = consent_id

        confirmed = AirwallexPaymentService._request(
            db,
            "POST",
            f"/api/v1/pa/payment_intents/{intent_id}/confirm",
            payload=confirm_payload,
        )
        return {
            "payment_intent_id": intent_id,
            "status": str(confirmed.get("status") or intent.get("status") or "").upper(),
            "intent": confirmed,
        }

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
        return AirwallexBillingService.charge_managed_payment(
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
    def intent_amount_minor(intent: dict[str, Any]) -> int:
        captured = intent.get("captured_amount") or intent.get("amount")
        if captured is not None:
            return int(round(float(captured) * 100))
        return 0

    @staticmethod
    def handle_renewal_payment_success(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        from app.models.plan import Plan
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

        amount_minor = AirwallexBillingService.intent_amount_minor(intent)
        currency = str(intent.get("currency") or sub.billing_currency or "GBP").upper()
        ext_inv = f"sub-renewal:{sub.id}:{period_key}" if period_key else f"sub-renewal:{sub.id}:{pid}"
        existing = InvoiceService.get_by_external(db, provider="airwallex", external_invoice_id=ext_inv)
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
                provider="airwallex",
                external_invoice_id=ext_inv,
                payment_reference=pid,
                payment_method="airwallex",
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
                db, sub=sub, provider="airwallex", period_key=period_key
            )
        BillingLifecycleService._advance_subscription_period(db, sub, plan)
        return {"ok": True, "renewal_paid": True, "invoice_id": invoice.id, "subscription_id": sub.id}
