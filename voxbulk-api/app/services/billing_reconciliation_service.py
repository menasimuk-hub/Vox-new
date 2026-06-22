"""Campaign billing reconciliation — refund unused launch charges to wallet."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_call_minutes import billable_call_minutes
from app.services.billing_currency import resolve_org_currency

logger = logging.getLogger(__name__)


class BillingReconciliationService:
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
    def already_reconciled(order: ServiceOrder) -> bool:
        return bool(BillingReconciliationService._load_snapshot(order).get("reconciliation"))

    @staticmethod
    def _recipient_result(recipient) -> dict[str, Any]:
        try:
            data = json.loads(recipient.result_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _actual_whatsapp_units(db: Session, order: ServiceOrder, *, trigger: str) -> int:
        from app.services.platform_catalog_service import ServiceOrderService

        recipients = ServiceOrderService.get_recipients(db, order.id)
        billable_statuses = {"completed", "in_progress"}
        if trigger == "cancellation":
            billable_statuses.add("sent")
        count = 0
        for recipient in recipients:
            status = str(recipient.status or "").lower()
            if status in billable_statuses:
                count += 1
        return max(0, count)

    @staticmethod
    def _actual_phone_cost(db: Session, snapshot: dict[str, Any], order: ServiceOrder, *, trigger: str) -> int:
        from app.services.platform_catalog_service import ServiceOrderService

        per_min = int(snapshot.get("unit_rate_minor") or 0)
        connection_fee = int(snapshot.get("connection_fee_minor") or 0)
        duration_per_call = max(1, int(snapshot.get("duration_minutes") or 1))

        recipients = ServiceOrderService.get_recipients(db, order.id)
        total_minutes = 0
        connected_calls = 0
        for recipient in recipients:
            status = str(recipient.status or "").lower()
            if status not in {"completed", "calling"} and trigger != "cancellation":
                continue
            if trigger == "cancellation" and status in {"pending", "cancelled"}:
                continue
            result = BillingReconciliationService._recipient_result(recipient)
            secs = None
            for key in ("duration_seconds", "duration_secs", "duration"):
                raw = result.get(key)
                if raw is not None:
                    try:
                        secs = int(raw)
                        break
                    except (TypeError, ValueError):
                        pass
            if secs is None and status == "completed":
                total_minutes += duration_per_call
                connected_calls += 1
                continue
            if secs and secs > 0:
                total_minutes += billable_call_minutes(secs)
                connected_calls += 1
            elif status in {"completed", "calling"}:
                total_minutes += duration_per_call
                connected_calls += 1

        return total_minutes * per_min + connected_calls * connection_fee

    @staticmethod
    def compute_actual_minor(db: Session, order: ServiceOrder, snapshot: dict[str, Any], *, trigger: str) -> int:
        charged = int(snapshot.get("wallet_charge_minor") or 0) + int(snapshot.get("dd_charge_minor") or 0)
        if charged <= 0:
            return 0

        channel = str(snapshot.get("channel") or "").lower()
        if channel == "whatsapp":
            unit_rate = int(snapshot.get("unit_rate_minor") or 0)
            units = BillingReconciliationService._actual_whatsapp_units(db, order, trigger=trigger)
            return units * unit_rate
        if channel in {"ai_call", "phone"}:
            return BillingReconciliationService._actual_phone_cost(db, snapshot, order, trigger=trigger)
        return charged

    @staticmethod
    def reconcile_order(
        db: Session,
        order: ServiceOrder,
        *,
        trigger: str,
    ) -> dict[str, Any] | None:
        """Refund unused launch charges to wallet with a credit note. Idempotent per order."""
        if order.payment_status != "approved":
            return None
        snapshot = BillingReconciliationService._load_snapshot(order)
        if snapshot.get("reconciliation"):
            return snapshot["reconciliation"]

        charged = int(snapshot.get("wallet_charge_minor") or 0) + int(snapshot.get("dd_charge_minor") or 0)
        if charged <= 0:
            return None

        org = db.get(Organisation, order.org_id)
        if org is None:
            return None

        actual = BillingReconciliationService.compute_actual_minor(db, order, snapshot, trigger=trigger)
        refund_minor = max(0, charged - actual)
        if refund_minor <= 0:
            snapshot["reconciliation"] = {
                "trigger": trigger,
                "charged_minor": charged,
                "actual_minor": actual,
                "refund_minor": 0,
                "reconciled_at": datetime.utcnow().isoformat(),
            }
            BillingReconciliationService._save_snapshot(db, order, snapshot)
            return snapshot["reconciliation"]

        from app.services.billing_lifecycle_service import BillingLifecycleService

        currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
        reason = (
            f"Campaign {trigger} reconciliation — {order.title}"[:500]
        )
        invoice_id = snapshot.get("invoice_id")
        result = BillingLifecycleService.issue_wallet_refund(
            db,
            org,
            amount_minor=refund_minor,
            currency=currency,
            reason=reason,
            order_id=order.id,
            invoice_id=str(invoice_id) if invoice_id else None,
            trigger=trigger,
        )
        snapshot["reconciliation"] = {
            "trigger": trigger,
            "charged_minor": charged,
            "actual_minor": actual,
            "refund_minor": refund_minor,
            "credit_note_id": result.get("credit_note_id"),
            "wallet_transaction_id": result.get("wallet_transaction_id"),
            "reconciled_at": datetime.utcnow().isoformat(),
        }
        BillingReconciliationService._save_snapshot(db, order, snapshot)
        logger.info(
            "billing_reconciled order_id=%s trigger=%s charged=%s actual=%s refund=%s",
            order.id,
            trigger,
            charged,
            actual,
            refund_minor,
        )
        return snapshot["reconciliation"]

    @staticmethod
    def on_order_terminal(db: Session, order: ServiceOrder, *, trigger: str) -> None:
        from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService

        CampaignBillingSettlementService.on_order_terminal(db, order, trigger=trigger)
