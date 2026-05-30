"""Interview billing mode helpers (package vs credits vs pay-as-you-go)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.gocardless_service import BillingService

# Wallet-only / no-subscription tiers — CV inbox collection is package-only.
CV_EMAIL_BLOCKED_PLAN_CODES = frozenset({"payg", "free", "topup"})

# Recruitment subscription tiers that include careers@ CV collection.
CV_EMAIL_INCLUDED_PLAN_CODES = frozenset(
    {
        "starter",
        "pro",
        "business",
        "enterprise",
        "practice",
        "group",
    }
)


def plan_allows_cv_email(plan: Plan | None) -> bool:
    if plan is None:
        return False
    code = str(plan.code or "").strip().lower()
    if code in CV_EMAIL_BLOCKED_PLAN_CODES:
        return False
    if code in CV_EMAIL_INCLUDED_PLAN_CODES:
        return True
    if plan.is_enterprise:
        return True
    interval = str(plan.interval or "monthly").strip().lower()
    price = plan.price_gbp_pence
    return interval == "monthly" and price is not None and int(price) > 0


def org_interview_billing_context(db: Session, org: Organisation) -> dict:
    BillingService.repair_subscription_plan_id(db, org.id)
    sub = BillingService.get_subscription(db, org.id)
    plan = BillingService.resolve_active_plan(db, org.id)
    if sub is not None and str(sub.status or "").strip().lower() == "pending_payment" and sub.pending_plan_id:
        pending = db.get(Plan, sub.pending_plan_id)
        if pending is not None and plan_allows_cv_email(pending):
            plan = pending
    status = str(sub.status or "").strip().lower() if sub else ""
    plan_code = str(plan.code or "").strip().lower() if plan else None

    cv_email_allowed = plan_allows_cv_email(plan)
    has_active_package = (
        sub is not None
        and status in {"active", "trial", "past_due"}
        and cv_email_allowed
    )

    interview_credits = int(org.interview_credits_balance or 0)
    if has_active_package:
        mode = "package"
    elif interview_credits > 0:
        mode = "credits"
    else:
        mode = "payg"

    block_reason: str | None = None
    if not cv_email_allowed:
        if plan_code in CV_EMAIL_BLOCKED_PLAN_CODES or mode == "payg":
            block_reason = "CV email collection is included on Starter, Pro, and Business packages — not on Pay as you go or top-up only."
        elif plan is None:
            block_reason = "Subscribe to a monthly package (Starter, Pro, or Business) to collect CVs by email."
        else:
            block_reason = f"CV email collection is not included on the {plan.name} plan."

    return {
        "billing_mode": mode,
        "cv_email_allowed": cv_email_allowed,
        "cv_email_block_reason": block_reason,
        "interview_credits": interview_credits,
        "has_active_subscription": has_active_package,
        "plan_name": plan.name if plan else None,
        "plan_code": plan_code,
    }
