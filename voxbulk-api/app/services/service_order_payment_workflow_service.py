"""Paid service-order workflow — invoice issuance, email, audit, launch readiness."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.invoice_service import InvoiceService
from app.services.org_audit_service import OrgAuditService

logger = logging.getLogger(__name__)

_NON_INVOICE_METHODS = frozenset({"promo_credits", "subscription_allowance"})


class ServiceOrderPaymentWorkflowError(ValueError):
    pass


class ServiceOrderPaymentWorkflowService:
    @staticmethod
    def _launch_billing_snapshot(order: ServiceOrder) -> dict[str, Any]:
        raw = order.launch_billing_json
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def requires_payment_invoice(order: ServiceOrder) -> bool:
        """Chargeable paid orders must have a linked invoice before launch."""
        if str(order.payment_status or "").lower() != "approved":
            return False
        method = str(order.payment_method or "").lower()
        if method in _NON_INVOICE_METHODS:
            return False
        quote = int(order.quote_total_pence or 0)
        snapshot = ServiceOrderPaymentWorkflowService._launch_billing_snapshot(order)
        wallet_charge = int(snapshot.get("wallet_charge_minor") or 0)
        dd_charge = int(snapshot.get("dd_charge_minor") or 0)
        if quote <= 0 and wallet_charge <= 0 and dd_charge <= 0:
            return False
        return True

    @staticmethod
    def resolve_payment_invoice_id(db: Session, order: ServiceOrder) -> str | None:
        if getattr(order, "payment_invoice_id", None):
            return str(order.payment_invoice_id)
        snapshot = ServiceOrderPaymentWorkflowService._launch_billing_snapshot(order)
        inv_id = snapshot.get("invoice_id")
        if inv_id:
            return str(inv_id)
        for external_id in (f"order-{order.id}", f"launch-{order.id}"):
            inv = InvoiceService.get_by_external(db, provider="internal", external_invoice_id=external_id)
            if inv is None and external_id.startswith("launch-"):
                inv = InvoiceService.get_by_external(db, provider="gocardless", external_invoice_id=external_id)
            if inv is not None:
                return inv.id
        inv = InvoiceService.get_for_order(db, order_id=order.id)
        return inv.id if inv is not None else None

    @staticmethod
    def link_payment_invoice(db: Session, order: ServiceOrder, invoice_id: str, *, commit: bool = True) -> None:
        order.payment_invoice_id = invoice_id
        if not getattr(order, "payment_invoice_issued_at", None):
            order.payment_invoice_issued_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        if commit:
            db.commit()
            db.refresh(order)

    @staticmethod
    def confirm_payment_and_issue_invoice(
        db: Session,
        order: ServiceOrder,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        commit_payment: bool = True,
    ) -> dict[str, Any]:
        """Issue (or reuse) invoice for a paid/chargeable order. Email failure does not block."""
        from app.services.org_control_center_actions_service import OrgControlCenterActionsService

        if not ServiceOrderPaymentWorkflowService.requires_payment_invoice(order):
            return {"ok": True, "skipped": True, "reason": "no_invoice_required"}

        existing_id = ServiceOrderPaymentWorkflowService.resolve_payment_invoice_id(db, order)
        if existing_id:
            ServiceOrderPaymentWorkflowService.link_payment_invoice(db, order, existing_id, commit=commit_payment)
            return {"ok": True, "invoice_id": existing_id, "created": False}

        result = OrgControlCenterActionsService.issue_order_payment_invoice(
            db,
            order,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        if not result or not result.get("invoice"):
            raise ServiceOrderPaymentWorkflowError(
                "Could not issue invoice — check billing email and order quote before launch"
            )
        invoice_id = str(result["invoice"]["id"])
        ServiceOrderPaymentWorkflowService.link_payment_invoice(db, order, invoice_id, commit=commit_payment)

        emailed = bool(result.get("emailed"))
        OrgAuditService.record_admin(
            db,
            org_id=order.org_id,
            event_type="order.payment_confirmed",
            action=f"Order payment confirmed — invoice {result['invoice'].get('invoice_number') or invoice_id[:8]}",
            entity_type="service_order",
            entity_id=order.id,
            metadata={"invoice_id": invoice_id, "emailed": emailed},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        if emailed:
            OrgAuditService.record_admin(
                db,
                org_id=order.org_id,
                event_type="invoice.emailed",
                action=f"Invoice emailed for order {order.id[:8]}",
                entity_type="invoice",
                entity_id=invoice_id,
                metadata={"order_id": order.id},
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        return {"ok": True, "invoice_id": invoice_id, "created": bool(result.get("created")), "emailed": emailed}

    @staticmethod
    def assert_launch_ready(db: Session, order: ServiceOrder) -> None:
        if str(order.payment_status or "").lower() != "approved":
            raise ServiceOrderPaymentWorkflowError("Payment must be completed before launch")
        if not ServiceOrderPaymentWorkflowService.requires_payment_invoice(order):
            return
        invoice_id = ServiceOrderPaymentWorkflowService.resolve_payment_invoice_id(db, order)
        if invoice_id:
            if not getattr(order, "payment_invoice_id", None):
                ServiceOrderPaymentWorkflowService.link_payment_invoice(db, order, invoice_id)
            return
        try:
            ServiceOrderPaymentWorkflowService.confirm_payment_and_issue_invoice(db, order)
        except ServiceOrderPaymentWorkflowError:
            raise
        except Exception as exc:
            logger.exception("launch_invoice_issue_failed order_id=%s", order.id)
            raise ServiceOrderPaymentWorkflowError(
                "Invoice must be issued before launch — fix billing contact or use admin resend"
            ) from exc
