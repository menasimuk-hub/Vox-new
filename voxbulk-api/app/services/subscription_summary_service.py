"""Customer-facing subscription finance summaries for Core and Customer Feedback."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.billing_finance_service import BillingFinanceService
from app.services.customer_feedback.billing_service import FEEDBACK_SERVICE_CODE, FeedbackBillingService


class SubscriptionSummaryService:
    @staticmethod
    def _finance_for_sub(
        db: Session,
        sub: Subscription | None,
        *,
        org: Organisation,
    ) -> dict[str, Any] | None:
        if sub is None:
            return None
        plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
        BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan, commit=True)
        return BillingFinanceService.subscription_finance_dict(db, sub, org=org, plan=plan)

    @staticmethod
    def core_summary(db: Session, org_id: str) -> dict[str, Any] | None:
        org = db.get(Organisation, org_id)
        if org is None:
            return None
        sub = BillingAccessService.get_valid_core_subscription(db, org_id)
        return SubscriptionSummaryService._finance_for_sub(db, sub, org=org)

    @staticmethod
    def feedback_summary(db: Session, org_id: str) -> dict[str, Any] | None:
        org = db.get(Organisation, org_id)
        if org is None:
            return None
        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return None
        finance = SubscriptionSummaryService._finance_for_sub(db, sub, org=org)
        if finance is None:
            return None
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        return {
            **finance,
            "service_code": FEEDBACK_SERVICE_CODE,
            "wa_units_included": usage.get("wa_units_included", 0),
            "wa_units_used": usage.get("wa_units_used", 0),
            "wa_units_remaining": usage.get("wa_units_remaining", 0),
        }

    @staticmethod
    def build_org_summary(db: Session, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            return {"ok": False, "core": None, "feedback": None}
        from app.services.billing_currency import resolve_org_currency

        return {
            "ok": True,
            "currency": resolve_org_currency(db, org),
            "core": SubscriptionSummaryService.core_summary(db, org_id),
            "feedback": SubscriptionSummaryService.feedback_summary(db, org_id),
        }
