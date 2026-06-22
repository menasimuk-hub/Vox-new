"""Appointment Manager billing — uses core platform subscription/package pool (not wallet top-up only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.survey_billing_context import org_survey_billing_context

SUBSCRIPTION_REQUIRED_MSG = (
    "Appointment Manager requires an active platform subscription package. "
    "Wallet top-up alone is not sufficient — subscribe under Account → Billing."
)


class AppointmentBillingError(ValueError):
    pass


class AppointmentBillingService:
    @staticmethod
    def operations_allowed(billing: dict[str, Any]) -> bool:
        """True when org can send WA / place AI calls via package subscription (same pool as surveys)."""
        return bool(billing.get("can_launch_and_invoice"))

    @staticmethod
    def eligibility(db: Session, org: Organisation) -> dict[str, Any]:
        billing = org_survey_billing_context(db, org)
        allowed = AppointmentBillingService.operations_allowed(billing)
        remaining = int(billing.get("package_remaining") or billing.get("whatsapp_remaining") or 0)
        return {
            "allowed": allowed,
            "reason": None if allowed else SUBSCRIPTION_REQUIRED_MSG,
            "requires_subscription": True,
            "topup_only_blocked": bool(billing.get("is_payg_plan")),
            "plan_name": billing.get("plan_name"),
            "plan_code": billing.get("plan_code"),
            "package_remaining": remaining,
            "whatsapp_remaining": int(billing.get("whatsapp_remaining") or 0),
            "has_active_subscription": bool(billing.get("has_active_subscription")),
            "can_launch_and_invoice": bool(billing.get("can_launch_and_invoice")),
        }

    @staticmethod
    def assert_can_operate(db: Session, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise AppointmentBillingError("Organisation not found")
        payload = AppointmentBillingService.eligibility(db, org)
        if not payload.get("allowed"):
            raise AppointmentBillingError(str(payload.get("reason") or SUBSCRIPTION_REQUIRED_MSG))
        return payload
