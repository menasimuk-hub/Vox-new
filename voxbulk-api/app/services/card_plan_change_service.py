"""Plan upgrades/downgrades for Stripe / Airwallex managed subscriptions (Phase 5)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.invoice_service import InvoiceService
from app.services.plan_price_service import PlanPriceService
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)

PRO_RATA_UPGRADE_KIND = "pro_rata_upgrade"


class CardPlanChangeError(ValueError):
    pass


class CardPlanChangeService:
    @staticmethod
    def is_managed(sub: Subscription | None) -> bool:
        from app.services.airwallex_billing_service import AirwallexBillingService
        from app.services.stripe_billing_service import StripeBillingService

        return StripeBillingService.is_managed_subscription(sub) or AirwallexBillingService.is_managed_subscription(
            sub
        )

    @staticmethod
    def apply_downgrade(
        db: Session,
        *,
        sub: Subscription,
        new_plan: Plan,
        billing_interval: str,
    ) -> dict[str, Any]:
        sub.pending_plan_id = new_plan.id
        sub.billing_interval = billing_interval
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return {"pending_plan_id": new_plan.id}

    @staticmethod
    def apply_upgrade_with_pro_rata(
        db: Session,
        *,
        org_id: str,
        sub: Subscription,
        old_plan: Plan,
        new_plan: Plan,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise CardPlanChangeError("Organisation not found")

        provider = str(sub.payment_provider or "").lower()
        if provider not in {"stripe", "airwallex"}:
            raise CardPlanChangeError("Unsupported payment provider for card plan change")
        if not CardPlanChangeService.is_managed(sub):
            raise CardPlanChangeError("Saved payment method is missing — update billing and try again")

        pro_rata = BillingLifecycleService.calculate_pro_rata_minor(
            db, org=org, sub=sub, old_plan=old_plan, new_plan=new_plan
        )
        currency = PlanPriceService.rates_for_org(db, org, plan=new_plan)["currency"]
        email = UsageWalletService.get_org_billing_email(db, org_id) or (org.contact_email or "")
        invoice_id: str | None = None
        external_id = f"pro-rata:{sub.id}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        desc = f"Pro-rata upgrade to {new_plan.name}"

        invoice = None
        if pro_rata > 0:
            invoice = InvoiceService.create_from_payment(
                db,
                org_id=org_id,
                client_email=email or "billing@voxbulk.local",
                subtotal_pence=pro_rata,
                currency=str(currency),
                description=desc,
                provider=provider,
                external_invoice_id=external_id,
                payment_method=provider,
                status="pending",
                line_items=[
                    {
                        "description": desc,
                        "quantity": 1,
                        "unit_pence": pro_rata,
                        "total_pence": pro_rata,
                    }
                ],
                kind="pro_rata",
            )
            invoice_id = invoice.id

            try:
                if provider == "stripe":
                    from app.services.stripe_billing_service import StripeBillingError, StripeBillingService

                    charge = StripeBillingService.charge_managed_payment(
                        db,
                        org=org,
                        sub=sub,
                        plan=new_plan,
                        amount_minor=pro_rata,
                        currency=str(currency),
                        payment_kind=PRO_RATA_UPGRADE_KIND,
                        reference_key=external_id,
                        description=desc,
                        extra_metadata={"voxbulk_invoice_external_id": external_id},
                    )
                    ok = str(charge.get("status") or "").lower() == "succeeded"
                else:
                    from app.services.airwallex_billing_service import AirwallexBillingError, AirwallexBillingService

                    charge = AirwallexBillingService.charge_managed_payment(
                        db,
                        org=org,
                        sub=sub,
                        plan=new_plan,
                        amount_minor=pro_rata,
                        currency=str(currency),
                        payment_kind=PRO_RATA_UPGRADE_KIND,
                        reference_key=external_id,
                        description=desc,
                        extra_metadata={"voxbulk_invoice_external_id": external_id},
                    )
                    ok = str(charge.get("status") or "").upper() == "SUCCEEDED"
            except Exception as exc:
                CardPlanChangeService._mark_invoice_failed_and_notify(
                    db,
                    org=org,
                    invoice=invoice,
                    plan=new_plan,
                    failure_reason=str(exc),
                )
                raise CardPlanChangeError(f"Pro-rata payment failed: {exc}") from exc

            if not ok:
                CardPlanChangeService._mark_invoice_failed_and_notify(
                    db,
                    org=org,
                    invoice=invoice,
                    plan=new_plan,
                    failure_reason=f"Card charge status {charge.get('status')}",
                    payment_reference=charge.get("payment_intent_id"),
                )
                raise CardPlanChangeError("Pro-rata payment was not successful")

            invoice.status = "paid"
            invoice.dd_status = "confirmed"
            pid = str(charge.get("payment_intent_id") or "")
            if pid:
                invoice.payment_reference = pid
            db.add(invoice)
            db.commit()
            db.refresh(invoice)

            try:
                from app.services.billing_event_email_service import BillingEventEmailService

                BillingEventEmailService.send_payment_receipt(db, invoice=invoice)
            except Exception:
                logger.exception("pro_rata_payment_receipt_email_failed invoice_id=%s", invoice.id)

        now = datetime.utcnow()
        sub.plan_id = new_plan.id
        sub.pending_plan_id = None
        sub.updated_at = now
        db.add(sub)
        db.commit()

        UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=new_plan, subscription=sub)
        return {"pro_rata_minor": pro_rata, "invoice_id": invoice_id, "plan_id": new_plan.id}

    @staticmethod
    def _mark_invoice_failed_and_notify(
        db: Session,
        *,
        org: Organisation,
        invoice,
        plan: Plan,
        failure_reason: str,
        payment_reference: str | None = None,
    ) -> None:
        from app.services.billing_currency import money_display
        from app.services.product_email_triggers import ProductEmailTriggers

        invoice.status = "failed"
        invoice.dd_status = "failed"
        if payment_reference:
            invoice.payment_reference = payment_reference
        db.add(invoice)
        db.commit()

        amount = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
        currency = str(invoice.currency or org.billing_currency or "GBP")
        try:
            ProductEmailTriggers.notify_payment_failed(
                db,
                to_email=invoice.client_email,
                extra_variables={
                    "plan_name": plan.name,
                    "amount_due": money_display(amount, currency),
                    "payment_status": "failed",
                    "failure_reason": failure_reason,
                    "org_name": org.name or "",
                    "invoice_number": invoice.invoice_number or invoice.external_invoice_id or invoice.id,
                },
            )
        except Exception:
            logger.exception("pro_rata_failure_email_failed invoice_id=%s", invoice.id)

    @staticmethod
    def handle_pro_rata_webhook_success(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        meta = intent.get("metadata") or {}
        ext_inv = str(meta.get("voxbulk_invoice_external_id") or "").strip()
        if not ext_inv:
            return {"ok": True, "ignored": True, "reason": "missing_invoice_ref"}

        invoice = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=ext_inv)
        if invoice is None:
            return {"ok": True, "ignored": True, "reason": "invoice_not_found"}
        if str(invoice.status or "").lower() == "paid":
            return {"ok": True, "duplicate": True, "invoice_id": invoice.id}

        pid = str(intent.get("id") or "").strip()
        invoice.status = "paid"
        invoice.dd_status = "confirmed"
        if pid:
            invoice.payment_reference = pid
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        try:
            from app.services.billing_event_email_service import BillingEventEmailService

            BillingEventEmailService.send_payment_receipt(db, invoice=invoice)
        except Exception:
            logger.exception("pro_rata_webhook_receipt_failed invoice_id=%s", invoice.id)

        return {"ok": True, "pro_rata_paid": True, "invoice_id": invoice.id}

    @staticmethod
    def handle_pro_rata_webhook_failure(
        db: Session,
        *,
        org: Organisation,
        intent: dict[str, Any],
        provider: str,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        meta = intent.get("metadata") or {}
        ext_inv = str(meta.get("voxbulk_invoice_external_id") or "").strip()
        if not ext_inv:
            return {"ok": True, "ignored": True, "reason": "missing_invoice_ref"}

        invoice = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=ext_inv)
        if invoice is None:
            return {"ok": True, "ignored": True, "reason": "invoice_not_found"}
        if str(invoice.status or "").lower() == "paid":
            return {"ok": True, "ignored": True, "reason": "already_paid"}

        from app.models.plan import Plan

        plan = db.get(Plan, str(meta.get("voxbulk_plan_id") or "")) or Plan(name="Subscription")
        CardPlanChangeService._mark_invoice_failed_and_notify(
            db,
            org=org,
            invoice=invoice,
            plan=plan,
            failure_reason=failure_reason or "Pro-rata payment failed",
            payment_reference=str(intent.get("id") or "") or None,
        )
        return {"ok": True, "pro_rata_failed": True, "invoice_id": invoice.id}

    @staticmethod
    def clear_stored_credentials(db: Session, sub: Subscription) -> bool:
        prov = str(sub.payment_provider or "").lower()
        if prov not in {"stripe", "airwallex"}:
            return False
        sub.external_customer_id = None
        sub.external_subscription_id = None
        sub.mandate_id = None
        sub.mandate_status = None
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        return True
