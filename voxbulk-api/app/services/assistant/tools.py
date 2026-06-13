from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_access_service import BillingAccessService
from app.services.billing_monitor_service import BillingMonitorService
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.schemas.dashboard import PlanOut, SubscriptionOut
from app.services.gocardless_service import BillingService
from app.services.invoice_service import InvoiceService
from app.services.platform_catalog_service import PlatformCatalogService as ServiceOrderService
from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityService
from app.services.survey_results_service import build_survey_results_payload
from app.services.support_ticket_service import SupportTicketService, ticket_to_dict
from app.services.usage_wallet_service import UsageWalletService
from app.services.wallet_service import WalletService


class AssistantTools:
    """Read-only in-process wrappers around existing VoxBulk services."""

    @staticmethod
    def get_org(db: Session, org_id: str) -> Organisation | None:
        return db.get(Organisation, org_id)

    @staticmethod
    def billing_access(db: Session, org: Organisation) -> dict[str, Any]:
        summary = BillingAccessService.access_summary(db, org)
        monitor = BillingMonitorService.build_for_org(db, org)
        status = monitor.get("status") or {}
        summary["billing_monitor"] = monitor
        summary["next_action"] = status.get("next_action")
        summary["next_action_label"] = status.get("next_action_label")
        return summary

    @staticmethod
    def billing_subscription(db: Session, org_id: str) -> dict[str, Any]:
        sub = BillingService.get_subscription(db, org_id)
        plan = BillingService.resolve_active_plan(db, org_id)
        return {
            "subscription": SubscriptionOut.model_validate(sub).model_dump() if sub else None,
            "plan": PlanOut.model_validate(plan).model_dump() if plan else None,
        }

    @staticmethod
    def usage_summary(db: Session, org: Organisation) -> dict[str, Any]:
        row = UsageWalletService.get_current(db, org.id)
        sub = BillingService.get_subscription(db, org.id)
        if row is None and sub is not None:
            try:
                row = UsageWalletService.bootstrap_from_plan(db, org_id=org.id, subscription=sub)
            except Exception:
                row = None
        usage_payload = UsageWalletService.summary_dict(row, db, org.id) if row else None
        monitor = BillingMonitorService.build_for_org(db, org, usage_row=row)
        wallet = WalletService.wallet_dict(db, org)
        return {"usage": usage_payload, "billing_monitor": monitor, "wallet": wallet}

    @staticmethod
    def wallet_transactions(db: Session, org_id: str, *, limit: int = 15) -> list[dict[str, Any]]:
        rows = WalletService.list_transactions(db, org_id, limit=limit)
        return [WalletService.transaction_to_dict(r) for r in rows]

    @staticmethod
    def invoices(db: Session, org_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = InvoiceService.list_for_org(db, org_id=org_id, limit=limit)
        return [InvoiceService.invoice_to_dict(r) for r in rows]

    @staticmethod
    def invoice_detail(db: Session, org_id: str, invoice_id: str) -> dict[str, Any] | None:
        row = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        return InvoiceService.invoice_to_dict(row) if row else None

    @staticmethod
    def list_service_orders(db: Session, org_id: str, *, service_code: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        rows = ServiceOrderService.list_orders(db, org_id=org_id, service_code=service_code, limit=limit)
        return [ServiceOrderService.order_to_dict(db, r) for r in rows]

    @staticmethod
    def service_order_detail(db: Session, org_id: str, order_id: str) -> dict[str, Any] | None:
        row = ServiceOrderService.get_order(db, order_id, org_id=org_id)
        return ServiceOrderService.order_to_dict(db, row) if row else None

    @staticmethod
    def launch_eligibility(db: Session, org: Organisation, order: ServiceOrder) -> dict[str, Any]:
        if order.service_code == "survey":
            return SurveyLaunchEligibilityService.compute(db, order, org)
        return {
            "can_launch": order.status not in {"archived", "stopped"},
            "order_id": order.id,
            "service_code": order.service_code,
            "status": order.status,
            "payment_status": order.payment_status,
        }

    @staticmethod
    def survey_results(db: Session, order: ServiceOrder) -> dict[str, Any]:
        return build_survey_results_payload(db, order, include_respondents=False)

    @staticmethod
    def interview_results(db: Session, order: ServiceOrder) -> dict[str, Any]:
        recipients = ServiceOrderService.get_recipients(db, order.id)
        completed = sum(1 for r in recipients if str(r.status or "").lower() in {"completed", "interviewed"})
        return {
            "order_id": order.id,
            "title": order.title,
            "recipient_count": len(recipients),
            "completed_count": completed,
            "status": order.status,
        }

    @staticmethod
    def feedback_locations(db: Session, org_id: str) -> list[dict[str, Any]]:
        return FeedbackLocationService.list_locations(db, org_id)

    @staticmethod
    def feedback_results(db: Session, org_id: str, *, location_id: str | None = None) -> dict[str, Any]:
        from app.services.customer_feedback.results_service import FeedbackResultsService

        return FeedbackResultsService.customer_results(db, org_id, location_id=location_id)

    @staticmethod
    def list_tickets(db: Session, org_id: str, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = SupportTicketService.list_customer_tickets(db, org_id=org_id, user_id=user_id, limit=limit)
        return [ticket_to_dict(db, r) for r in rows]

    @staticmethod
    def wallet_low_analysis(db: Session, org: Organisation) -> dict[str, Any]:
        wallet = WalletService.wallet_dict(db, org)
        txns = AssistantTools.wallet_transactions(db, org.id, limit=10)
        invoices = AssistantTools.invoices(db, org.id, limit=10)
        orders = AssistantTools.list_service_orders(db, org.id, limit=10)
        debits = [t for t in txns if str(t.get("direction") or "").lower() == "debit"]
        outstanding = [i for i in invoices if str(i.get("status") or "").lower() not in {"paid", "void", "cancelled", "refunded"}]
        paid_orders = [o for o in orders if str(o.get("payment_status") or "").lower() in {"paid", "completed"}]
        return {
            "wallet": wallet,
            "recent_debits": debits,
            "outstanding_invoices": outstanding,
            "recent_orders": paid_orders,
        }

    @staticmethod
    def pick_charge_explanation(analysis: dict[str, Any]) -> tuple[str, str | None, str | None, str]:
        """Return highlight_type, highlight_id, highlight_label, explanation fragment."""
        debits = analysis.get("recent_debits") or []
        if debits:
            top = debits[0]
            amt = top.get("amount_display") or top.get("description") or "a campaign charge"
            return (
                "wallet_transaction" if top.get("id") else "service_order",
                str(top.get("id") or top.get("order_id") or ""),
                str(top.get("description") or "Recent wallet debit")[:80],
                f"Your most recent wallet debit was {amt}.",
            )
        outstanding = analysis.get("outstanding_invoices") or []
        if outstanding:
            inv = outstanding[0]
            amt = inv.get("amount_display") or inv.get("total_display") or "an outstanding invoice"
            return (
                "invoice",
                str(inv.get("id") or ""),
                str(inv.get("invoice_number") or inv.get("description") or "Outstanding invoice")[:80],
                f"You have an outstanding invoice for {amt}.",
            )
        orders = analysis.get("recent_orders") or []
        if orders:
            o = orders[0]
            title = o.get("title") or "a recent campaign"
            quote = o.get("quote_total_gbp") or o.get("quote_total_display") or ""
            frag = f"Recent campaign “{title}”" + (f" was quoted at {quote}." if quote else ".")
            return ("service_order", str(o.get("id") or ""), str(title)[:80], frag)
        return ("usage", None, "Usage", "No recent debits or outstanding invoices were found. Check usage meters for allowance consumption.")
