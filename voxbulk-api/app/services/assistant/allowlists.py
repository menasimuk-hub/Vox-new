from __future__ import annotations

from typing import FrozenSet

# Read-only tools available to customer JWT principals (org-scoped).
CUSTOMER_READ_TOOLS: FrozenSet[str] = frozenset(
    {
        "billing_access",
        "billing_subscription",
        "usage_summary",
        "usage_breakdown",
        "wallet",
        "wallet_transactions",
        "invoices",
        "invoice_detail",
        "list_service_orders",
        "service_order_detail",
        "launch_eligibility",
        "survey_results",
        "interview_results",
        "feedback_locations",
        "feedback_results",
        "feedback_subscription",
        "list_tickets",
        "ticket_detail",
    }
)

# Mutations require explicit user confirmation via /assistant/confirm.
CUSTOMER_MUTATION_TOOLS: FrozenSet[str] = frozenset(
    {
        "create_support_ticket",
    }
)

# Admin-only read tools (cross-org where permitted by RBAC).
ADMIN_READ_TOOLS: FrozenSet[str] = frozenset(
    {
        "admin_support_kpis",
        "admin_list_tickets",
        "admin_ticket_detail",
        "admin_recent_invoices",
        "admin_invoice_detail",
        "admin_subscriptions",
        "admin_org_control_center",
    }
)

ADMIN_MUTATION_TOOLS: FrozenSet[str] = frozenset(
    {
        "admin_reply_ticket",
        "admin_assign_ticket",
    }
)


def customer_may_read(tool: str) -> bool:
    return tool in CUSTOMER_READ_TOOLS


def customer_may_mutate(tool: str) -> bool:
    return tool in CUSTOMER_MUTATION_TOOLS


def admin_may_read(tool: str) -> bool:
    return tool in ADMIN_READ_TOOLS


def admin_may_mutate(tool: str) -> bool:
    return tool in ADMIN_MUTATION_TOOLS
