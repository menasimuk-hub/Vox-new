"""Campaign launch billing — allowance → wallet → Direct Debit orchestration.

VoxBulk pricing model:
- Subscription customers: plan allowance covers launches first; any extra is invoiced and
  collected via the GoCardless mandate (Direct Debit).
- PAYG customers: launches are paid from the wallet only (topped up via Stripe/Airwallex).
  Launch is blocked when the wallet balance is insufficient.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)


class LaunchBillingError(ValueError):
    pass


class LaunchBillingService:
    # ------------------------------------------------------------------ estimates

    @staticmethod
    def estimate_whatsapp_launch(
        db: Session,
        org: Organisation,
        *,
        recipient_count: int,
        wa_remaining: int,
        has_subscription: bool,
    ) -> dict[str, Any]:
        from app.services.gocardless_service import BillingService
        from app.services.wallet_service import WalletService

        plan = BillingService.resolve_active_plan(db, org.id)
        rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        currency = str(rates["currency"])
        unit_rate = int(rates["wa_extra_minor"] or 0)

        count = max(0, int(recipient_count or 0))
        covered = min(max(0, int(wa_remaining or 0)), count) if has_subscription else 0
        billable = max(0, count - covered)
        total_minor = billable * unit_rate

        return LaunchBillingService._allocate_payment(
            db,
            org,
            currency=currency,
            total_minor=total_minor,
            collect_by_dd=has_subscription,
            base={
                "channel": "whatsapp",
                "unit": "recipients",
                "unit_rate_minor": unit_rate,
                "unit_rate_display": money_display(unit_rate, currency),
                "units_total": count,
                "units_covered_by_allowance": covered,
                "units_billable": billable,
                "wallet_balance_minor": WalletService.balance_minor(org),
            },
        )

    @staticmethod
    def estimate_phone_launch(
        db: Session,
        org: Organisation,
        *,
        recipient_count: int,
        duration_min: int,
        calls_remaining_min: int,
        has_subscription: bool,
    ) -> dict[str, Any]:
        from app.services.gocardless_service import BillingService
        from app.services.wallet_service import WalletService

        plan = BillingService.resolve_active_plan(db, org.id)
        rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        currency = str(rates["currency"])
        per_min = int(rates["interview_per_min_minor"] or 0)
        connection_fee = int(rates["connection_fee_minor"] or 0)

        count = max(0, int(recipient_count or 0))
        duration = max(1, int(duration_min or 1))
        estimated_minutes = duration * count
        covered_minutes = min(max(0, int(calls_remaining_min or 0)), estimated_minutes) if has_subscription else 0
        billable_minutes = max(0, estimated_minutes - covered_minutes)
        # Connection fees apply per call; covered allowance is minute based, fees are billable when PAYG
        connection_total = connection_fee * count if not has_subscription else 0
        total_minor = billable_minutes * per_min + connection_total

        return LaunchBillingService._allocate_payment(
            db,
            org,
            currency=currency,
            total_minor=total_minor,
            collect_by_dd=has_subscription,
            base={
                "channel": "ai_call",
                "unit": "minutes",
                "unit_rate_minor": per_min,
                "unit_rate_display": money_display(per_min, currency),
                "connection_fee_minor": connection_fee,
                "connection_fee_total_minor": connection_total,
                "per_call_minor": connection_fee + per_min * duration,
                "per_call_display": money_display(connection_fee + per_min * duration, currency),
                "duration_minutes": duration,
                "units_total": estimated_minutes,
                "units_covered_by_allowance": covered_minutes,
                "units_billable": billable_minutes,
                "recipient_count": count,
                "wallet_balance_minor": WalletService.balance_minor(org),
            },
        )

    @staticmethod
    def _allocate_payment(
        db: Session,
        org: Organisation,
        *,
        currency: str,
        total_minor: int,
        collect_by_dd: bool,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        """Split the billable amount across wallet and Direct Debit, in that order."""
        from app.services.wallet_service import WalletService

        wallet_balance = WalletService.balance_minor(org)
        total = max(0, int(total_minor or 0))

        if total <= 0:
            wallet_charge = 0
            dd_charge = 0
            method = "allowance"
            can_launch = True
            block_reason = None
        elif collect_by_dd:
            # Subscription customers: extras are invoiced and collected by Direct Debit at launch.
            wallet_charge = 0
            dd_charge = total
            method = "direct_debit"
            can_launch = True
            block_reason = None
        elif wallet_balance >= total:
            wallet_charge = total
            dd_charge = 0
            method = "wallet"
            can_launch = True
            block_reason = None
        else:
            wallet_charge = 0
            dd_charge = 0
            method = "blocked"
            can_launch = False
            shortfall = total - wallet_balance
            block_reason = (
                f"Wallet balance is insufficient — {money_display(total, currency)} required, "
                f"{money_display(wallet_balance, currency)} available. "
                f"Top up at least {money_display(shortfall, currency)} to launch."
            )

        return {
            **base,
            "currency": currency,
            "total_minor": total,
            "total_display": money_display(total, currency),
            "wallet_charge_minor": wallet_charge,
            "wallet_charge_display": money_display(wallet_charge, currency),
            "dd_charge_minor": dd_charge,
            "dd_charge_display": money_display(dd_charge, currency),
            "wallet_balance_minor": wallet_balance,
            "wallet_balance_display": money_display(wallet_balance, currency),
            "wallet_shortfall_minor": max(0, total - wallet_balance) if method == "blocked" else 0,
            "payment_method": method,
            "can_launch": can_launch,
            "block_reason": block_reason,
        }

    # ------------------------------------------------------------------ charging

    @staticmethod
    def charge_launch(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        breakdown: dict[str, Any],
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute the launch charge per the estimate breakdown. Idempotent per order."""
        if order.payment_status == "approved":
            return {"ok": True, "already_charged": True}
        if not breakdown.get("can_launch"):
            raise LaunchBillingError(str(breakdown.get("block_reason") or "Launch is blocked"))

        currency = str(breakdown.get("currency") or resolve_org_currency(db, org))
        wallet_charge = int(breakdown.get("wallet_charge_minor") or 0)
        dd_charge = int(breakdown.get("dd_charge_minor") or 0)
        result: dict[str, Any] = {"ok": True, "wallet_charged_minor": 0, "dd_charged_minor": 0, "invoice_id": None}

        if wallet_charge > 0:
            from app.services.wallet_service import WalletService

            tx = WalletService.debit(
                db,
                org,
                amount_minor=wallet_charge,
                kind="launch_debit",
                description=f"Campaign launch — {order.title}"[:500],
                order_id=order.id,
                created_by_user_id=user_id,
                metadata={"channel": breakdown.get("channel"), "units": breakdown.get("units_billable")},
                commit=False,
            )
            result["wallet_charged_minor"] = wallet_charge
            result["wallet_transaction_id"] = tx.id

        invoice = None
        if dd_charge > 0:
            invoice = LaunchBillingService._invoice_and_collect_dd(
                db,
                order,
                org,
                amount_minor=dd_charge,
                currency=currency,
                breakdown=breakdown,
            )
            result["dd_charged_minor"] = dd_charge
            result["invoice_id"] = invoice.id if invoice is not None else None

        snapshot = {
            **{k: v for k, v in breakdown.items() if not k.startswith("wallet_balance")},
            "charged_at": datetime.utcnow().isoformat(),
            "wallet_transaction_id": result.get("wallet_transaction_id"),
            "invoice_id": result.get("invoice_id"),
        }
        order.launch_billing_json = json.dumps(snapshot, ensure_ascii=False)
        order.payment_status = "approved"
        order.status = "paid"
        method = str(breakdown.get("payment_method") or "")
        order.payment_method = {
            "allowance": "subscription_allowance",
            "wallet": "wallet",
            "direct_debit": "gocardless_dd",
        }.get(method, method or "wallet")
        if method == "allowance":
            order.payment_note = "Covered by plan allowance"
        elif method == "wallet":
            order.payment_note = f"Paid from wallet ({money_display(wallet_charge, currency)})"
        elif method == "direct_debit":
            order.payment_note = f"Collected by Direct Debit ({money_display(dd_charge, currency)})"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        logger.info(
            "launch_billing_charged order_id=%s org_id=%s method=%s wallet=%s dd=%s",
            order.id, org.id, method, wallet_charge, dd_charge,
        )
        return result

    @staticmethod
    def _invoice_and_collect_dd(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        *,
        amount_minor: int,
        currency: str,
        breakdown: dict[str, Any],
    ) -> Any:
        """Create a campaign invoice and submit the Direct Debit against the org mandate."""
        from app.services.gocardless_service import (
            BillingService,
            GoCardlessConfigError,
            GoCardlessProviderError,
        )
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        if not email:
            raise LaunchBillingError("No billing email on file — add a billing contact before launch")

        units = int(breakdown.get("units_billable") or 0)
        unit_rate = int(breakdown.get("unit_rate_minor") or 0)
        channel = str(breakdown.get("channel") or "campaign")
        if channel == "whatsapp":
            desc = f"WhatsApp survey launch — {order.title} ({units} extra recipients)"
            line = {"description": f"WA survey recipients beyond allowance × {units}", "quantity": units, "unit_pence": unit_rate, "total_pence": amount_minor}
        else:
            desc = f"AI call campaign launch — {order.title} ({units} extra minutes)"
            line = {"description": f"AI call minutes beyond allowance × {units}", "quantity": units, "unit_pence": unit_rate, "total_pence": amount_minor}

        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org.id,
            client_email=email,
            subtotal_pence=amount_minor,
            currency=currency,
            description=desc,
            provider="gocardless",
            external_invoice_id=f"launch-{order.id}",
            payment_method="gocardless",
            status="pending",
            line_items=[line],
            kind="campaign",
            order_id=order.id,
        )

        # Submit the Direct Debit; a missing mandate/config or submission error never blocks the
        # launch for subscription customers — the invoice stays pending for recovery (Phase 2).
        payment = None
        try:
            payment = BillingService.collect_mandate_payment(
                db,
                org_id=org.id,
                amount_pence=amount_minor,
                description=desc,
                currency=currency,
                metadata={"invoice_id": invoice.id, "order_id": order.id},
            )
        except GoCardlessConfigError:
            logger.warning("launch_dd_not_configured invoice_id=%s org_id=%s", invoice.id, org.id)
            invoice.dd_status = "not_configured"
        except GoCardlessProviderError:
            logger.exception("launch_dd_submission_failed invoice_id=%s org_id=%s", invoice.id, org.id)
            invoice.dd_status = "submission_failed"

        if payment is not None:
            invoice.dd_payment_id = str(payment.get("payment_id") or "")
            invoice.dd_status = str(payment.get("status") or "pending_submission")
            invoice.payment_reference = invoice.dd_payment_id
            invoice.status = "collecting"
        else:
            invoice.dd_status = invoice.dd_status or "no_mandate"
            invoice.status = "pending"
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        try:
            from app.services.billing_event_email_service import BillingEventEmailService

            BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
        except Exception:
            logger.exception("launch_invoice_email_failed invoice_id=%s", invoice.id)
        return invoice
