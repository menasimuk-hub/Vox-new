"""Survey billing context — promo credits, subscription WhatsApp allowance, pay-as-you-go."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.gocardless_service import BillingService
from app.services.usage_wallet_service import UsageWalletService

ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trial", "past_due"})


def org_survey_billing_context(db: Session, org: Organisation) -> dict:
    BillingService.repair_subscription_plan_id(db, org.id)
    sub = BillingService.get_subscription(db, org.id)
    plan = BillingService.resolve_active_plan(db, org.id)
    status = str(sub.status or "").strip().lower() if sub else ""
    has_active_subscription = sub is not None and status in ACTIVE_SUBSCRIPTION_STATUSES

    usage = UsageWalletService.get_current(db, org.id)
    wa_included = int(usage.whatsapp_included or 0) if usage else 0
    wa_used = int(usage.whatsapp_used or 0) if usage else 0
    wa_remaining = max(0, wa_included - wa_used) if wa_included > 0 else 0
    usage_status = str(usage.status or "").strip().lower() if usage else ""
    has_whatsapp_allowance = usage is not None and wa_included > 0 and usage_status in {"active", "trial"}

    survey_credits = int(org.survey_credits_balance or 0)
    plan_code = str(plan.code or "").strip().lower() if plan else None

    return {
        "has_active_subscription": has_active_subscription or has_whatsapp_allowance,
        "has_whatsapp_allowance": has_whatsapp_allowance,
        "subscription_status": status or usage_status or None,
        "plan_name": plan.name if plan else (str(usage.plan_code or "").strip().title() if usage and usage.plan_code else None),
        "plan_code": plan_code or (str(usage.plan_code or "").strip().lower() if usage else None),
        "whatsapp_included": wa_included,
        "whatsapp_used": wa_used,
        "whatsapp_remaining": wa_remaining,
        "survey_credits": survey_credits,
        "payg_allowed": True,
    }
