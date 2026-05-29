"""Interview billing mode helpers (package vs credits vs pay-as-you-go)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.gocardless_service import BillingService


def org_interview_billing_context(db: Session, org: Organisation) -> dict:
    sub = BillingService.get_subscription(db, org.id)
    plan = BillingService.resolve_active_plan(db, org.id)
    status = str(sub.status or "").strip().lower() if sub else ""
    has_active_package = (
        sub is not None
        and status in {"active", "trial"}
        and plan is not None
    )
    interview_credits = int(org.interview_credits_balance or 0)
    if has_active_package:
        mode = "package"
    elif interview_credits > 0:
        mode = "credits"
    else:
        mode = "payg"

    return {
        "billing_mode": mode,
        "cv_email_allowed": has_active_package,
        "interview_credits": interview_credits,
        "has_active_subscription": has_active_package,
        "plan_name": plan.name if plan else None,
    }
