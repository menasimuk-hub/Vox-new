"""Campaign completion billing — actual call minutes, deferred invoices, wallet hold settlement."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_call_minutes import billable_call_minutes, call_outcome_label
from app.services.billing_currency import money_display, resolve_org_currency

logger = logging.getLogger(__name__)

_DEFERRED_PHASES = frozenset({"held", "pending_settlement"})
_PHONE_CHANNELS = frozenset({"ai_call", "phone", "call"})


class CampaignBillingSettlementService:
    @staticmethod
    def _load_snapshot(order: ServiceOrder) -> dict[str, Any]:
        raw = order.launch_billing_json
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _save_snapshot(db: Session, order: ServiceOrder, snapshot: dict[str, Any]) -> None:
        order.launch_billing_json = json.dumps(snapshot, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)

    @staticmethod
    def uses_deferred_settlement(order: ServiceOrder) -> bool:
        phase = str(CampaignBillingSettlementService._load_snapshot(order).get("billing_phase") or "")
        return phase in _DEFERRED_PHASES

    @staticmethod
    def _recipient_result(recipient) -> dict[str, Any]:
        try:
            data = json.loads(recipient.result_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _duration_seconds(result: dict[str, Any]) -> int | None:
        for key in ("duration_seconds", "duration_secs", "duration"):
            raw = result.get(key)
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _is_voicemail(result: dict[str, Any], hangup_cause: str) -> bool:
        if result.get("voicemail") or result.get("answering_machine"):
            return True
        cause = hangup_cause.lower()
        return any(token in cause for token in ("machine", "answering_machine", "voicemail"))

    @staticmethod
    def aggregate_phone_calls(db: Session, order: ServiceOrder, *, trigger: str) -> dict[str, Any]:
        from app.services.platform_catalog_service import ServiceOrderService

        recipients = ServiceOrderService.get_recipients(db, order.id)
        call_rows: list[dict[str, Any]] = []
        total_seconds = 0
        total_billable = 0
        connected = 0

        for recipient in recipients:
            status = str(recipient.status or "").lower()
            result = CampaignBillingSettlementService._recipient_result(recipient)
            hangup = str(result.get("hangup_cause") or "")
            voicemail = CampaignBillingSettlementService._is_voicemail(result, hangup)
            secs = CampaignBillingSettlementService._duration_seconds(result)
            stored_bm = result.get("billable_minutes")
            try:
                bm = int(stored_bm) if stored_bm is not None else billable_call_minutes(secs)
            except (TypeError, ValueError):
                bm = billable_call_minutes(secs)

            terminal_statuses = {"completed", "calling", "opted_out", "no_answer", "busy", "failed", "cancelled"}
            if status not in terminal_statuses and trigger != "cancellation":
                continue
            if trigger == "cancellation" and status in {"pending"}:
                continue

            if bm > 0:
                connected += 1
                total_seconds += max(0, int(secs or 0))
                total_billable += bm

            call_rows.append(
                {
                    "recipient_id": recipient.id,
                    "name": recipient.name,
                    "phone": recipient.phone,
                    "status": status,
                    "call_type": call_outcome_label(status=status, hangup_cause=hangup, voicemail=voicemail),
                    "hangup_cause": hangup or None,
                    "duration_seconds": secs,
                    "billable_minutes": bm,
                    "call_control_id": result.get("call_control_id"),
                }
            )

        return {
            "calls": call_rows,
            "total_duration_seconds": total_seconds,
            "total_billable_minutes": total_billable,
            "connected_calls": connected,
        }

    @staticmethod
    def _allowance_remaining_minutes(db: Session, org_id: str) -> int:
        from app.services.usage_wallet_service import UsageWalletService

        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return 0
        included = int(row.calls_included or 0)
        used = int(row.calls_used or 0)
        return max(0, included - used)

    @staticmethod
    def _compute_costs(
        db: Session,
        order: ServiceOrder,
        snapshot: dict[str, Any],
        usage: dict[str, Any],
        *,
        trigger: str,
    ) -> dict[str, Any]:
        channel = str(snapshot.get("channel") or "").lower()
        per_min = int(snapshot.get("unit_rate_minor") or 0)
        connection_fee = int(snapshot.get("connection_fee_minor") or 0)
        payment_method = str(snapshot.get("payment_method") or order.payment_method or "").lower()
        is_subscription = payment_method in {"allowance", "direct_debit", "gocardless_dd", "subscription_allowance"}

        if channel == "whatsapp":
            from app.services.billing_reconciliation_service import BillingReconciliationService

            units = BillingReconciliationService._actual_whatsapp_units(db, order, trigger=trigger)
            covered_est = int(snapshot.get("units_covered_by_allowance") or 0)
            if is_subscription:
                remaining = CampaignBillingSettlementService._allowance_remaining_minutes(db, order.org_id)
                # WA allowance is recipient count, not minutes
                from app.services.usage_wallet_service import UsageWalletService

                wa_row = UsageWalletService.get_current(db, order.org_id)
                wa_remaining = 0
                if wa_row is not None:
                    wa_remaining = max(0, int(wa_row.wa_included or 0) - int(wa_row.wa_used or 0))
                included_units = min(units, wa_remaining)
                extra_units = max(0, units - included_units)
            else:
                included_units = 0
                extra_units = units
            unit_rate = int(snapshot.get("unit_rate_minor") or 0)
            final_minor = extra_units * unit_rate
            return {
                "channel": channel,
                "actual_units": units,
                "included_units": included_units,
                "extra_units": extra_units,
                "extra_minutes": 0,
                "included_minutes": included_units,
                "total_billable_minutes": 0,
                "final_charge_minor": final_minor,
                "connection_fee_minor": 0,
                "per_min_rate_minor": unit_rate,
                "is_subscription": is_subscription,
            }

        total_billable = int(usage.get("total_billable_minutes") or 0)
        connected = int(usage.get("connected_calls") or 0)

        if is_subscription:
            remaining = CampaignBillingSettlementService._allowance_remaining_minutes(db, order.org_id)
            included_minutes = min(total_billable, remaining)
            extra_minutes = max(0, total_billable - included_minutes)
        else:
            included_minutes = 0
            extra_minutes = total_billable

        conn_total = connection_fee * connected if not is_subscription else 0
        minute_charge = extra_minutes * per_min if is_subscription else total_billable * per_min
        final_minor = minute_charge + conn_total

        return {
            "channel": channel,
            "total_billable_minutes": total_billable,
            "included_minutes": included_minutes,
            "extra_minutes": extra_minutes,
            "connected_calls": connected,
            "final_charge_minor": final_minor,
            "connection_fee_minor": conn_total,
            "per_min_rate_minor": per_min,
            "is_subscription": is_subscription,
        }

    @staticmethod
    def _issue_completion_invoice(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        *,
        amount_minor: int,
        currency: str,
        line_items: list[dict[str, Any]],
        description: str,
        collect_dd: bool,
    ) -> str | None:
        if amount_minor <= 0:
            return None
        from app.services.invoice_line_item_service import InvoiceLineItemService
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        if not email:
            logger.warning("completion_invoice_no_email order_id=%s", order.id)
            return None

        charge_amount = InvoiceLineItemService.gross_total_pence(line_items) or amount_minor
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org.id,
            client_email=email,
            subtotal_pence=charge_amount,
            currency=currency,
            description=description[:255],
            provider="gocardless" if collect_dd else "internal",
            external_invoice_id=f"completion-{order.id}",
            payment_method="gocardless" if collect_dd else "wallet",
            status="pending",
            line_items=line_items,
            kind="campaign",
            order_id=order.id,
        )

        if collect_dd:
            from app.services.gocardless_service import (
                BillingService,
                GoCardlessConfigError,
                GoCardlessProviderError,
            )

            try:
                payment = BillingService.collect_mandate_payment(
                    db,
                    org_id=org.id,
                    amount_pence=int(invoice.amount_gbp_pence or charge_amount),
                    description=description[:255],
                    currency=currency,
                    metadata={"invoice_id": invoice.id, "order_id": order.id},
                )
                if payment is not None:
                    invoice.dd_payment_id = str(payment.get("payment_id") or "")
                    invoice.dd_status = str(payment.get("status") or "pending_submission")
                    invoice.payment_reference = invoice.dd_payment_id
                    invoice.status = "collecting"
            except GoCardlessConfigError:
                invoice.dd_status = "not_configured"
            except GoCardlessProviderError:
                logger.exception("completion_dd_failed invoice_id=%s", invoice.id)
                invoice.dd_status = "submission_failed"
            db.add(invoice)
            db.commit()

        try:
            from app.services.billing_event_email_service import BillingEventEmailService

            BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
        except Exception:
            logger.exception("completion_invoice_email_failed invoice_id=%s", invoice.id)

        from app.services.service_order_payment_workflow_service import ServiceOrderPaymentWorkflowService

        ServiceOrderPaymentWorkflowService.link_payment_invoice(db, order, invoice.id)
        return invoice.id

    @staticmethod
    def settle_order(db: Session, order: ServiceOrder, *, trigger: str) -> dict[str, Any] | None:
        """Settle deferred billing at campaign end. Idempotent."""
        if order.payment_status != "approved":
            return None

        snapshot = CampaignBillingSettlementService._load_snapshot(order)
        if snapshot.get("settlement"):
            return snapshot["settlement"]
        if str(snapshot.get("billing_phase") or "") not in _DEFERRED_PHASES:
            return None

        org = db.get(Organisation, order.org_id)
        if org is None:
            return None

        channel = str(snapshot.get("channel") or "").lower()
        usage = (
            CampaignBillingSettlementService.aggregate_phone_calls(db, order, trigger=trigger)
            if channel in _PHONE_CHANNELS
            else {"calls": [], "total_billable_minutes": 0, "connected_calls": 0, "total_duration_seconds": 0}
        )
        costs = CampaignBillingSettlementService._compute_costs(db, order, snapshot, usage, trigger=trigger)
        currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
        final_minor = int(costs.get("final_charge_minor") or 0)
        payment_method = str(snapshot.get("payment_method") or order.payment_method or "").lower()
        is_subscription = bool(costs.get("is_subscription"))
        collect_dd = is_subscription and final_minor > 0 and payment_method in {
            "direct_debit",
            "gocardless_dd",
        }

        invoice_id = None
        if final_minor > 0:
            from app.services.invoice_line_item_service import InvoiceLineItemService

            line_items = InvoiceLineItemService.from_actual_call_usage(
                costs,
                order_title=str(order.title or ""),
                channel=channel,
            )
            if channel in _PHONE_CHANNELS:
                desc = (
                    f"AI call campaign — {order.title} "
                    f"({costs.get('extra_minutes') or costs.get('total_billable_minutes')} min actual)"
                )
            else:
                desc = f"WhatsApp campaign — {order.title} ({costs.get('extra_units', 0)} extra recipients)"
            invoice_id = CampaignBillingSettlementService._issue_completion_invoice(
                db,
                order,
                org,
                amount_minor=final_minor,
                currency=currency,
                line_items=line_items,
                description=desc,
                collect_dd=collect_dd,
            )
        elif is_subscription:
            logger.info("completion_no_invoice order_id=%s within allowance", order.id)

        hold_minor = int(snapshot.get("wallet_hold_minor") or snapshot.get("wallet_charge_minor") or 0)
        hold_refund = 0
        if hold_minor > 0:
            from app.services.billing_lifecycle_service import BillingLifecycleService

            hold_refund = max(0, hold_minor - final_minor)
            if hold_refund > 0:
                BillingLifecycleService.issue_wallet_refund(
                    db,
                    org,
                    amount_minor=hold_refund,
                    currency=currency,
                    reason=f"Campaign {trigger} — unused launch hold — {order.title}"[:500],
                    order_id=order.id,
                    invoice_id=invoice_id,
                    trigger=trigger,
                )
            elif final_minor > hold_minor:
                from app.services.wallet_service import WalletService

                WalletService.debit(
                    db,
                    org,
                    amount_minor=final_minor - hold_minor,
                    kind="launch_debit",
                    description=f"Campaign completion top-up — {order.title}"[:500],
                    order_id=order.id,
                )

        # Record actual usage against plan allowance
        if channel in _PHONE_CHANNELS and int(usage.get("total_billable_minutes") or 0) > 0:
            from app.services.usage_wallet_service import UsageWalletService

            UsageWalletService.record_call_usage(
                db,
                org_id=order.org_id,
                units=int(usage.get("total_billable_minutes") or 0),
            )
        elif channel == "whatsapp" and int(costs.get("actual_units") or 0) > 0:
            from app.services.usage_wallet_service import UsageWalletService

            UsageWalletService.record_whatsapp_usage(
                db,
                org_id=order.org_id,
                units=int(costs.get("actual_units") or 0),
            )

        settlement = {
            "trigger": trigger,
            "settled_at": datetime.utcnow().isoformat(),
            "final_charge_minor": final_minor,
            "hold_minor": hold_minor,
            "hold_refund_minor": hold_refund,
            "invoice_id": invoice_id,
            "total_billable_minutes": costs.get("total_billable_minutes"),
            "included_minutes": costs.get("included_minutes"),
            "extra_minutes": costs.get("extra_minutes"),
            "extra_units": costs.get("extra_units"),
            "included_units": costs.get("included_units"),
            "call_records": usage.get("calls") or [],
        }
        snapshot["settlement"] = settlement
        snapshot["billing_phase"] = "settled"
        if invoice_id:
            snapshot["invoice_id"] = invoice_id
        CampaignBillingSettlementService._save_snapshot(db, order, snapshot)
        logger.info(
            "campaign_settled order_id=%s trigger=%s final=%s extra_min=%s invoice=%s",
            order.id,
            trigger,
            final_minor,
            costs.get("extra_minutes"),
            invoice_id,
        )
        return settlement

    @staticmethod
    def on_order_terminal(db: Session, order: ServiceOrder, *, trigger: str) -> None:
        try:
            if CampaignBillingSettlementService.uses_deferred_settlement(order):
                CampaignBillingSettlementService.settle_order(db, order, trigger=trigger)
            else:
                from app.services.billing_reconciliation_service import BillingReconciliationService

                BillingReconciliationService.reconcile_order(db, order, trigger=trigger)
        except Exception:
            logger.exception("campaign_billing_terminal_failed order_id=%s trigger=%s", order.id, trigger)
