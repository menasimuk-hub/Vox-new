"""Survey billing context — promo credits, subscription WhatsApp allowance, pay-as-you-go."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.gocardless_service import BillingService
from app.services.package_entitlement_service import PackageEntitlementService
from app.services.usage_wallet_service import UsageWalletService

ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trial", "past_due"})
PAYG_PLAN_CODES = frozenset({"payg", "free", "topup"})


def org_survey_billing_context(db: Session, org: Organisation) -> dict:
    BillingService.repair_subscription_plan_id(db, org.id)
    sub = BillingService.get_subscription(db, org.id)
    plan = BillingService.resolve_active_plan(db, org.id)
    status = str(sub.status or "").strip().lower() if sub else ""
    has_dd_subscription = sub is not None and status in ACTIVE_SUBSCRIPTION_STATUSES

    usage = UsageWalletService.get_current(db, org.id)
    entitlement = PackageEntitlementService.for_org(db, org, usage)

    if entitlement.get("shared_package_pool"):
        wa_included = int(entitlement.get("package_included") or 0)
        wa_used = int(entitlement.get("package_used") or 0)
        wa_remaining = int(entitlement.get("package_remaining") or 0)
        calls_included = wa_included
        calls_used = wa_used
        calls_remaining = wa_remaining
    else:
        wa_included = int(usage.whatsapp_included or 0) if usage else 0
        wa_used = int(usage.whatsapp_used or 0) if usage else 0
        wa_remaining = max(0, wa_included - wa_used) if wa_included > 0 else 0
        calls_included = int(usage.calls_included or 0) if usage else 0
        calls_used = int(usage.calls_used or 0) if usage else 0
        calls_remaining = max(0, calls_included - calls_used) if calls_included > 0 else 0

    usage_status = str(usage.status or "").strip().lower() if usage else ""
    has_whatsapp_allowance = usage is not None and (wa_included > 0 or int(usage.whatsapp_included or 0) > 0) and usage_status in {"active", "trial"}
    has_call_allowance = usage is not None and (calls_included > 0 or int(usage.calls_included or 0) > 0) and usage_status in {"active", "trial"}

    survey_credits = int(org.survey_credits_balance or 0)
    plan_code = str(plan.code or "").strip().lower() if plan else None
    if not plan_code and usage and usage.plan_code:
        plan_code = str(usage.plan_code or "").strip().lower()

    is_payg_plan = plan_code in PAYG_PLAN_CODES or (plan is None and not has_whatsapp_allowance)
    can_launch_and_invoice = has_whatsapp_allowance or (has_dd_subscription and not is_payg_plan)

    from app.services.billing_monitor_service import BillingMonitorService

    billing_monitor = BillingMonitorService.build_for_org(db, org, usage_row=usage)
    commercial = billing_monitor.get("commercial") or {}
    estimates = billing_monitor.get("capacity_estimates") or {}

    return {
        "has_active_subscription": has_dd_subscription or has_whatsapp_allowance,
        "has_dd_subscription": has_dd_subscription,
        "has_whatsapp_allowance": has_whatsapp_allowance,
        "can_launch_and_invoice": can_launch_and_invoice,
        "is_payg_plan": is_payg_plan,
        "subscription_status": status or usage_status or None,
        "plan_name": plan.name if plan else (str(usage.plan_code or "").strip().title() if usage and usage.plan_code else None),
        "plan_code": plan_code or (str(usage.plan_code or "").strip().lower() if usage else None),
        "launch_allowance_units": int(entitlement.get("package_remaining") or wa_remaining) if entitlement.get("shared_package_pool") else wa_remaining,
        "whatsapp_included": wa_included,
        "whatsapp_used": wa_used,
        "whatsapp_remaining": wa_remaining,
        "calls_included": calls_included,
        "calls_used": calls_used,
        "calls_remaining": calls_remaining,
        "has_call_allowance": has_call_allowance,
        "survey_credits": survey_credits,
        "payg_allowed": True,
        "shared_package_pool": bool(entitlement.get("shared_package_pool")),
        "value_pool": entitlement.get("value_pool") or {},
        "package_included": int(entitlement.get("package_included") or 0),
        "package_used": int(entitlement.get("package_used") or 0),
        "package_remaining": int(entitlement.get("package_remaining") or 0),
        "package_remaining_pence": int(commercial.get("package_remaining_pence") or 0),
        "package_remaining_display": commercial.get("package_remaining_display"),
        "wallet_balance_display": commercial.get("wallet_balance_display"),
        "channel_calls_used": int(entitlement.get("calls_used") or calls_used),
        "channel_whatsapp_used": int(entitlement.get("whatsapp_used") or wa_used),
        "estimated_wa_surveys": int(estimates.get("estimated_wa_surveys") or 0),
        "estimated_ai_minutes": int(estimates.get("estimated_ai_minutes") or 0),
        "estimate_source": estimates.get("source"),
        "estimate_label": estimates.get("label"),
        "billing_monitor": billing_monitor,
    }
