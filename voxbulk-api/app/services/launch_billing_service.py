"""Campaign launch billing — allowance → wallet → Direct Debit orchestration.

VoxBulk pricing model:
- Plan allowance covers launches first.
- Billable extras: wallet is charged when balance is sufficient (subscription or PAYG).
- Remaining billable amount on subscription: invoiced and collected via Direct Debit.
- PAYG without sufficient wallet: launch blocked until top-up.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.plan_price_service import PlanPriceService

logger = logging.getLogger(__name__)

# PAYG launches hold 125% of estimated cost to cover calls running longer than estimate.
PAYG_WALLET_BUFFER_MULTIPLIER = 1.25


class LaunchBillingError(ValueError):
    pass


class LaunchBillingService:
    # ------------------------------------------------------------------ estimates

    @staticmethod
    def _rate_snapshot(db: Session, org: Organisation, plan) -> dict[str, Any]:
        rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        return {
            "currency": str(rates["currency"]),
            "per_min_minor": int(rates["per_min_minor"] or 0),
            "extra_per_min_minor": int(rates["extra_per_min_minor"] or 0),
            "list_per_min_minor": int(rates.get("interview_per_min_minor") or rates["per_min_minor"] or 0),
            "connection_fee_minor": int(rates["connection_fee_minor"] or 0),
            "wa_package_fee_minor": int(rates["wa_package_fee_minor"] or 0),
            "wa_extra_minor": int(rates["wa_extra_minor"] or 0),
        }

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
        rate_snap = LaunchBillingService._rate_snapshot(db, org, plan)
        currency = rate_snap["currency"]
        wa_package = rate_snap["wa_package_fee_minor"]
        wa_extra = rate_snap["wa_extra_minor"]

        count = max(0, int(recipient_count or 0))
        covered = min(max(0, int(wa_remaining or 0)), count) if has_subscription else 0
        billable = max(0, count - covered)
        catalog_minor = count * (wa_package if has_subscription else wa_extra)
        amount_due_minor = billable * wa_extra

        breakdown = LaunchBillingService._allocate_payment(
            db,
            org,
            currency=currency,
            total_minor=amount_due_minor,
            collect_by_dd=has_subscription,
            base={
                "channel": "whatsapp",
                "unit": "recipients",
                "unit_rate_minor": wa_extra,
                "unit_rate_display": money_display(wa_extra, currency),
                "wa_package_fee_minor": wa_package,
                "wa_extra_minor": wa_extra,
                "per_min_minor": rate_snap["per_min_minor"],
                "extra_per_min_minor": rate_snap["extra_per_min_minor"],
                "list_per_min_minor": rate_snap["list_per_min_minor"],
                "connection_fee_minor": rate_snap["connection_fee_minor"],
                "units_total": count,
                "units_covered_by_allowance": covered,
                "units_billable": billable,
                "catalog_cost_minor": catalog_minor,
                "catalog_cost_display": money_display(catalog_minor, currency),
                "amount_due_minor": amount_due_minor,
                "amount_due_display": money_display(amount_due_minor, currency),
                "wa_remaining_at_launch": max(0, int(wa_remaining or 0)) if has_subscription else 0,
            },
        )
        return breakdown

    @staticmethod
    def estimate_phone_launch(
        db: Session,
        org: Organisation,
        *,
        recipient_count: int,
        duration_min: int,
        calls_remaining_min: int,
        has_subscription: bool,
        voice_channel: str = "ai_call",
    ) -> dict[str, Any]:
        from app.services.gocardless_service import BillingService
        from app.services.wallet_service import WalletService

        plan = BillingService.resolve_active_plan(db, org.id)
        rate_snap = LaunchBillingService._rate_snapshot(db, org, plan)
        currency = rate_snap["currency"]
        per_min_bundle = rate_snap["per_min_minor"]
        extra_per_min = rate_snap["extra_per_min_minor"]
        list_per_min = rate_snap["list_per_min_minor"]
        connection_fee = rate_snap["connection_fee_minor"]

        count = max(0, int(recipient_count or 0))
        duration = max(1, int(duration_min or 1))
        estimated_minutes = duration * count
        covered_minutes = min(max(0, int(calls_remaining_min or 0)), estimated_minutes) if has_subscription else 0
        billable_minutes = max(0, estimated_minutes - covered_minutes)
        connection_total = connection_fee * count
        if has_subscription:
            catalog_minor = estimated_minutes * per_min_bundle + connection_total
            amount_due_minor = billable_minutes * extra_per_min + (connection_total if billable_minutes > 0 else 0)
        else:
            catalog_minor = estimated_minutes * list_per_min + connection_total
            amount_due_minor = catalog_minor

        channel = str(voice_channel or "ai_call").strip().lower()
        if channel not in {"ai_call", "ai_meeting", "meeting", "phone", "call"}:
            channel = "ai_call"
        if channel == "meeting":
            channel = "ai_meeting"

        return LaunchBillingService._allocate_payment(
            db,
            org,
            currency=currency,
            total_minor=amount_due_minor,
            collect_by_dd=has_subscription,
            base={
                "channel": channel,
                "unit": "minutes",
                "unit_rate_minor": list_per_min if not has_subscription else per_min_bundle,
                "unit_rate_display": money_display(list_per_min if not has_subscription else per_min_bundle, currency),
                "per_min_minor": per_min_bundle,
                "extra_per_min_minor": extra_per_min,
                "list_per_min_minor": list_per_min,
                "connection_fee_minor": connection_fee,
                "connection_fee_total_minor": connection_total,
                "wa_package_fee_minor": rate_snap["wa_package_fee_minor"],
                "wa_extra_minor": rate_snap["wa_extra_minor"],
                "per_call_minor": connection_fee + (list_per_min if not has_subscription else per_min_bundle) * duration,
                "per_call_display": money_display(
                    connection_fee + (list_per_min if not has_subscription else per_min_bundle) * duration,
                    currency,
                ),
                "duration_minutes": duration,
                "units_total": estimated_minutes,
                "units_covered_by_allowance": covered_minutes,
                "units_billable": billable_minutes,
                "recipient_count": count,
                "catalog_cost_minor": catalog_minor,
                "catalog_cost_display": money_display(catalog_minor, currency),
                "amount_due_minor": amount_due_minor,
                "amount_due_display": money_display(amount_due_minor, currency),
                "calls_remaining_at_launch": max(0, int(calls_remaining_min or 0)) if has_subscription else 0,
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
        """Split the billable amount across wallet first, then Direct Debit for subscription."""
        from app.services.wallet_service import WalletService

        wallet_balance = WalletService.spendable_minor(org, allow_promo=False)
        total_balance = WalletService.balance_minor(org)
        estimated_cost = max(0, int(total_minor or 0))
        required_wallet = (
            math.ceil(estimated_cost * PAYG_WALLET_BUFFER_MULTIPLIER)
            if estimated_cost > 0 and not collect_by_dd
            else estimated_cost
        )

        if estimated_cost <= 0:
            wallet_charge = 0
            dd_charge = 0
            method = "allowance"
            can_launch = True
            block_reason = None
        elif collect_by_dd and wallet_balance >= estimated_cost:
            wallet_charge = estimated_cost
            dd_charge = 0
            method = "wallet"
            can_launch = True
            block_reason = None
        elif collect_by_dd:
            wallet_charge = 0
            dd_charge = estimated_cost
            method = "direct_debit"
            can_launch = True
            block_reason = None
        elif wallet_balance >= required_wallet:
            wallet_charge = required_wallet
            dd_charge = 0
            method = "wallet"
            can_launch = True
            block_reason = None
        else:
            wallet_charge = 0
            dd_charge = 0
            method = "blocked"
            can_launch = False
            shortfall = required_wallet - wallet_balance
            hold_display = money_display(required_wallet, currency)
            est_display = money_display(estimated_cost, currency)
            block_reason = (
                f"Estimated cost {est_display}. We hold 125% ({hold_display}) for longer calls. "
                f"Your wallet has {money_display(wallet_balance, currency)} available for launches"
                f"{f' ({money_display(total_balance, currency)} total, including promo credit that cannot be used here)' if total_balance > wallet_balance else ''}"
                f" — top up at least {money_display(shortfall, currency)} to launch."
            )

        return {
            **base,
            "currency": currency,
            "estimated_cost_minor": estimated_cost,
            "estimated_cost_display": money_display(estimated_cost, currency),
            "required_wallet_minor": required_wallet if not collect_by_dd else estimated_cost,
            "required_wallet_display": money_display(
                required_wallet if not collect_by_dd else estimated_cost, currency
            ),
            "wallet_buffer_percent": int(PAYG_WALLET_BUFFER_MULTIPLIER * 100) if not collect_by_dd else 100,
            "total_minor": estimated_cost,
            "total_display": money_display(estimated_cost, currency),
            "wallet_charge_minor": wallet_charge,
            "wallet_charge_display": money_display(wallet_charge, currency),
            "dd_charge_minor": dd_charge,
            "dd_charge_display": money_display(dd_charge, currency),
            "wallet_balance_minor": total_balance,
            "wallet_balance_display": money_display(total_balance, currency),
            "wallet_spendable_minor": wallet_balance,
            "wallet_spendable_display": money_display(wallet_balance, currency),
            "wallet_shortfall_minor": max(0, required_wallet - wallet_balance) if method == "blocked" else 0,
            "top_up_minor": max(0, required_wallet - wallet_balance) if method == "blocked" else 0,
            "top_up_display": money_display(max(0, required_wallet - wallet_balance), currency)
            if method == "blocked"
            else None,
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

        method = str(breakdown.get("payment_method") or "")
        is_payg_hold = method == "wallet" and dd_charge <= 0 and wallet_charge > 0

        if wallet_charge > 0:
            from app.services.wallet_service import InsufficientWalletBalance, WalletService

            try:
                tx = WalletService.debit(
                    db,
                    org,
                    amount_minor=wallet_charge,
                    kind="launch_hold" if is_payg_hold else "launch_debit",
                    description=(
                        f"Campaign launch hold — {order.title}" if is_payg_hold else f"Campaign launch — {order.title}"
                    )[:500],
                    order_id=order.id,
                    created_by_user_id=user_id,
                    metadata={"channel": breakdown.get("channel"), "units": breakdown.get("units_billable")},
                    restrict_promo_spend=True,
                    commit=False,
                )
            except InsufficientWalletBalance as exc:
                raise LaunchBillingError(str(exc)) from exc
            result["wallet_charged_minor"] = wallet_charge
            result["wallet_transaction_id"] = tx.id

        # Deferred settlement: no invoice at launch (PAYG hold or subscription).
        invoice = None
        if dd_charge > 0:
            result["dd_deferred_minor"] = dd_charge

        billing_phase = "held" if is_payg_hold else "pending_settlement"
        snapshot = {
            **{k: v for k, v in breakdown.items() if not k.startswith("wallet_balance")},
            "charged_at": datetime.utcnow().isoformat(),
            "wallet_transaction_id": result.get("wallet_transaction_id"),
            "wallet_hold_minor": wallet_charge if wallet_charge > 0 else 0,
            "billing_phase": billing_phase,
            "invoice_id": None,
        }
        order.launch_billing_json = json.dumps(snapshot, ensure_ascii=False)
        order.payment_status = "approved"
        order.status = "paid"
        order.payment_method = {
            "allowance": "subscription_allowance",
            "wallet": "wallet",
            "direct_debit": "gocardless_dd",
        }.get(method, method or "wallet")
        if method == "allowance":
            order.payment_note = "Covered by plan allowance"
        elif method == "wallet":
            if is_payg_hold:
                order.payment_note = f"Wallet hold {money_display(wallet_charge, currency)} — invoice after campaign"
            else:
                order.payment_note = f"Paid from wallet ({money_display(wallet_charge, currency)})"
        elif method == "direct_debit":
            order.payment_note = "Subscription launch — invoice after campaign for extra usage"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        logger.info(
            "launch_billing_charged order_id=%s org_id=%s method=%s wallet_hold=%s phase=%s",
            order.id,
            org.id,
            method,
            wallet_charge,
            billing_phase,
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
        from app.services.invoice_line_item_service import InvoiceLineItemService

        line_items = InvoiceLineItemService.from_launch_breakdown(breakdown, order_title=str(order.title or ""))
        if channel == "whatsapp":
            desc = f"WhatsApp survey launch — {order.title} ({units} extra recipients)"
        else:
            desc = f"AI call campaign launch — {order.title} ({units} extra minutes)"
        charge_amount = InvoiceLineItemService.gross_total_pence(line_items) or amount_minor

        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org.id,
            client_email=email,
            subtotal_pence=charge_amount,
            currency=currency,
            description=desc,
            provider="gocardless",
            external_invoice_id=f"launch-{order.id}",
            payment_method="gocardless",
            status="pending",
            line_items=line_items,
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
                amount_pence=int(invoice.amount_gbp_pence or charge_amount),
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
