"""Unified visible workflow state for service orders — dashboard + admin."""

from __future__ import annotations

from typing import Any

from app.models.service_order import ServiceOrder

PAID_STATUSES = frozenset({"paid", "approved"})
RUNNING_STATUSES = frozenset({"running", "paused", "scheduled"})
TERMINAL_STATUSES = frozenset({"completed", "cancelled"})


class ServiceOrderWorkflowService:
    @staticmethod
    def visible_state(order: ServiceOrder) -> dict[str, Any]:
        status = str(order.status or "draft").strip().lower()
        payment_status = str(order.payment_status or "unpaid").strip().lower()
        payment_method = str(order.payment_method or "").strip().lower()

        if status in TERMINAL_STATUSES:
            workflow = "completed" if status == "completed" else "cancelled"
        elif status in RUNNING_STATUSES:
            workflow = "launched" if status == "running" else status
        elif status == "paused" and payment_status in PAID_STATUSES:
            workflow = "stopped"
        elif payment_status == "pending_approval" or status == "awaiting_payment":
            workflow = "payment_pending"
        elif payment_status == "rejected":
            workflow = "cancelled"
        elif status == "quoted" or (status == "draft" and order.quote_total_pence):
            workflow = "quoted"
        elif payment_status in PAID_STATUSES and status in {"paid", "draft", "quoted"}:
            workflow = "launch_ready"
        elif status == "draft":
            workflow = "draft"
        else:
            workflow = status or "draft"

        if payment_status in PAID_STATUSES and workflow in {"quoted", "draft", "paid"}:
            workflow = "launch_ready"

        label_map = {
            "draft": "Draft",
            "quoted": "Quoted",
            "payment_pending": "Payment pending",
            "launch_ready": "Launch ready",
            "launched": "Launched",
            "running": "Running",
            "scheduled": "Scheduled",
            "paused": "Paused",
            "stopped": "Stopped",
            "completed": "Completed",
            "cancelled": "Cancelled",
        }

        pay_action = None
        if workflow == "quoted":
            pay_action = "pay_quote"
        elif workflow == "payment_pending":
            pay_action = "await_admin_approval"
        elif workflow == "launch_ready":
            pay_action = "launch"
        elif payment_status == "unpaid" and status not in TERMINAL_STATUSES:
            pay_action = "pay_to_launch"

        return {
            "workflow_state": workflow,
            "workflow_label": label_map.get(workflow, workflow.replace("_", " ").title()),
            "status": status,
            "payment_status": payment_status,
            "payment_method": payment_method or None,
            "pay_action": pay_action,
            "can_launch": payment_status in PAID_STATUSES and status not in TERMINAL_STATUSES.union(RUNNING_STATUSES),
            "can_pay": payment_status in {"unpaid", "pending_approval"} and status not in TERMINAL_STATUSES,
            "is_running": status in RUNNING_STATUSES,
        }
