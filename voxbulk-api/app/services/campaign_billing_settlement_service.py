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

_DEFERRED_PHASES = frozenset({"held", "pending_settlement", "billing_failed"})
_VOICE_BILLING_CHANNELS = frozenset({"ai_call", "ai_meeting", "phone", "call", "meeting"})


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
                    "email": recipient.email,
                    "status": status,
                    "call_type": call_outcome_label(status=status, hangup_cause=hangup, voicemail=voicemail),
                    "hangup_cause": hangup or None,
                    "duration_seconds": secs,
                    "billable_minutes": bm,
                    "call_control_id": result.get("call_control_id"),
                    "telnyx_conversation_id": result.get("telnyx_conversation_id") or result.get("conversation_id"),
                    "call_channel": result.get("channel") or result.get("call_channel"),
                    "transport": result.get("transport"),
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
        from app.models.organisation import Organisation
        from app.services.campaign_running_cost_service import CampaignRunningCostService

        org = db.get(Organisation, order.org_id)
        if org is None:
            return {"final_charge_minor": 0, "catalog_cost_minor": 0}

        channel = str(snapshot.get("channel") or "").lower()
        unmetered = 0
        if order.service_code == "interview":
            from app.services.interview_session_billing_service import unmetered_billable_minutes
            from app.services.platform_catalog_service import ServiceOrderService

            recipients = ServiceOrderService.get_recipients(db, order.id)
            unmetered = unmetered_billable_minutes(recipients)

        if channel == "whatsapp":
            from app.services.billing_reconciliation_service import BillingReconciliationService

            units = BillingReconciliationService._actual_whatsapp_units(db, order, trigger=trigger)
            costs = CampaignRunningCostService.compute_whatsapp(db, order, org, snapshot, actual_units=units)
        else:
            costs = CampaignRunningCostService.compute_voice(
                db,
                order,
                org,
                snapshot,
                usage,
                unmetered_billable=unmetered,
                service_code=order.service_code or "",
            )
        return costs

    @staticmethod
    def _sync_overage_invoiced(db: Session, org_id: str, *, amount_minor: int) -> None:
        if amount_minor <= 0:
            return
        from app.services.usage_wallet_service import UsageWalletService

        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return
        row.overage_invoiced_pence = int(row.overage_invoiced_pence or 0) + amount_minor
        row.last_overage_invoice_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()

    @staticmethod
    def _issue_completion_invoice(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        *,
        amount_minor: int,
        catalog_minor: int,
        currency: str,
        line_items: list[dict[str, Any]],
        description: str,
        collect_dd: bool,
    ) -> str | None:
        from app.services.invoice_line_item_service import InvoiceLineItemService
        from app.services.invoice_service import InvoiceService
        from app.services.usage_wallet_service import UsageWalletService

        if not line_items:
            return None

        email = UsageWalletService.get_org_billing_email(db, org.id) or (org.contact_email or "")
        if not email:
            logger.warning("completion_invoice_no_email order_id=%s", order.id)
            return None

        charge_amount = max(0, int(amount_minor))
        due_total = InvoiceLineItemService.amount_due_pence(line_items)
        if due_total > 0:
            charge_amount = due_total
        is_paid = charge_amount <= 0

        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org.id,
            client_email=email,
            subtotal_pence=charge_amount,
            currency=currency,
            description=description[:255],
            provider="gocardless" if collect_dd and not is_paid else "internal",
            external_invoice_id=f"completion-{order.id}",
            payment_method="subscription_allowance" if is_paid else ("gocardless" if collect_dd else "wallet"),
            status="paid" if is_paid else "pending",
            line_items=line_items,
            kind="campaign",
            order_id=order.id,
        )
        if catalog_minor > charge_amount and is_paid:
            invoice.description = (description[:200] + f" — campaign value {money_display(catalog_minor, currency)}")[:255]
            db.add(invoice)
            db.commit()

        if collect_dd and not is_paid:
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
        phase = str(snapshot.get("billing_phase") or "")
        if phase not in _DEFERRED_PHASES:
            return None
        if phase == "billing_failed":
            snapshot.pop("billing_failure", None)
            snapshot["billing_phase"] = "pending_settlement"

        org = db.get(Organisation, order.org_id)
        if org is None:
            return None

        channel = str(snapshot.get("channel") or "").lower()
        is_voice = channel in _VOICE_BILLING_CHANNELS or order.service_code == "interview"
        usage = (
            CampaignBillingSettlementService.aggregate_phone_calls(db, order, trigger=trigger)
            if is_voice
            else {"calls": [], "total_billable_minutes": 0, "connected_calls": 0, "total_duration_seconds": 0}
        )
        costs = CampaignBillingSettlementService._compute_costs(db, order, snapshot, usage, trigger=trigger)
        currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
        final_minor = int(costs.get("amount_due_minor") or costs.get("final_charge_minor") or 0)
        catalog_minor = int(costs.get("catalog_cost_minor") or final_minor)
        payment_method = str(snapshot.get("payment_method") or order.payment_method or "").lower()
        is_subscription = bool(costs.get("is_subscription"))
        collect_dd = is_subscription and final_minor > 0 and payment_method in {
            "direct_debit",
            "gocardless_dd",
        }

        has_activity = (
            int(costs.get("total_billable_minutes") or 0) > 0
            or int(costs.get("actual_units") or 0) > 0
            or int(usage.get("connected_calls") or 0) > 0
        )

        invoice_id = None
        if has_activity:
            from app.services.invoice_line_item_service import InvoiceLineItemService

            line_items = InvoiceLineItemService.from_campaign_settlement(
                costs,
                order_title=str(order.title or ""),
                channel=channel,
                service_code=str(order.service_code or ""),
            )
            if is_voice:
                sc = str(order.service_code or "").lower()
                label = "AI interview" if sc == "interview" else "AI call survey"
                mins = costs.get("total_billable_minutes") or 0
                desc = f"{label} — {order.title} ({mins} min actual)"
            else:
                desc = f"WhatsApp survey — {order.title} ({costs.get('actual_units', 0)} surveys)"
            invoice_id = CampaignBillingSettlementService._issue_completion_invoice(
                db,
                order,
                org,
                amount_minor=final_minor,
                catalog_minor=catalog_minor,
                currency=currency,
                line_items=line_items,
                description=desc,
                collect_dd=collect_dd,
            )
            if invoice_id and final_minor > 0:
                CampaignBillingSettlementService._sync_overage_invoiced(db, order.org_id, amount_minor=final_minor)

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
                from app.services.wallet_service import InsufficientWalletBalance, WalletService

                try:
                    WalletService.debit(
                        db,
                        org,
                        amount_minor=final_minor - hold_minor,
                        kind="launch_debit",
                        description=f"Campaign completion top-up — {order.title}"[:500],
                        order_id=order.id,
                    )
                except InsufficientWalletBalance as exc:
                    snapshot["billing_phase"] = "billing_failed"
                    snapshot["billing_failure"] = {
                        "reason": "insufficient_wallet",
                        "message": str(exc),
                        "failed_at": datetime.utcnow().isoformat(),
                        "amount_minor": final_minor - hold_minor,
                    }
                    CampaignBillingSettlementService._save_snapshot(db, order, snapshot)
                    raise

        if is_voice:
            from app.services.interview_session_billing_service import unmetered_billable_minutes
            from app.services.platform_catalog_service import ServiceOrderService

            recipients = ServiceOrderService.get_recipients(db, order.id)
            units = unmetered_billable_minutes(recipients)
            if units > 0:
                from app.services.usage_wallet_service import UsageWalletService

                UsageWalletService.record_call_usage(
                    db,
                    org_id=order.org_id,
                    units=units,
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
            "catalog_cost_minor": catalog_minor,
            "amount_due_minor": final_minor,
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
        except Exception as exc:
            logger.exception("campaign_billing_terminal_failed order_id=%s trigger=%s", order.id, trigger)
            snapshot = CampaignBillingSettlementService._load_snapshot(order)
            if str(snapshot.get("billing_phase") or "") in _DEFERRED_PHASES:
                snapshot["billing_phase"] = "billing_failed"
                snapshot["billing_failure"] = {
                    "reason": type(exc).__name__,
                    "message": str(exc)[:500],
                    "failed_at": datetime.utcnow().isoformat(),
                    "trigger": trigger,
                }
                CampaignBillingSettlementService._save_snapshot(db, order, snapshot)
            try:
                from app.workers.billing_tasks import retry_campaign_settlement

                retry_campaign_settlement.delay(order.id, trigger)
            except Exception:
                logger.exception("campaign_settlement_retry_enqueue_failed order_id=%s", order.id)
