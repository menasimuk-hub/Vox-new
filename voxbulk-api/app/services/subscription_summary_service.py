"""Customer-facing subscription finance summaries for Core, Feedback, and Smart Card."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.billing_finance_service import BillingFinanceService
from app.services.customer_feedback.billing_service import FEEDBACK_SERVICE_CODE, FeedbackBillingService
from app.models.smart_card import SMART_CARD_SERVICE_CODE


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
        if sub is not None:
            status = str(sub.status or "").lower()
            if status in {"cancelled", "canceled", "inactive", "expired"}:
                sub = None
            else:
                plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
                code = str(getattr(plan, "code", "") or "").lower()
                is_payg = code == "payg" or bool(getattr(plan, "is_payg", False))
                if is_payg:
                    return {
                        "plan_name": (plan.name if plan else None) or "Pay as you go",
                        "plan_code": plan.code if plan else "payg",
                        "status": status or "active",
                        "billing_interval": None,
                        "next_billing_date": None,
                        "amount_next_payment_display": "Pay as you go",
                        "amount_next_payment_minor": 0,
                        "current_period_end": None,
                        "cancel_at_period_end": False,
                        "is_payg": True,
                        "service_code": "voxbulk",
                    }
                if status not in {"active", "trial", "past_due", "pending_first_payment"}:
                    sub = None

        finance = SubscriptionSummaryService._finance_for_sub(db, sub, org=org)
        if finance is None:
            # PAYG / linked plan without a paid subscription row — still surface plan name.
            from app.services.billing_access_service import BillingAccessService as BAS

            payg_sub = BAS.get_subscription(db, org_id, service_code="voxbulk")
            if payg_sub is not None:
                plan = db.get(Plan, payg_sub.plan_id) if payg_sub.plan_id else None
                code = str(getattr(plan, "code", "") or "").lower()
                if plan and (code == "payg" or bool(getattr(plan, "is_payg", False))):
                    return {
                        "plan_name": plan.name or "Pay as you go",
                        "plan_code": plan.code,
                        "status": str(payg_sub.status or "active"),
                        "billing_interval": None,
                        "next_billing_date": None,
                        "amount_next_payment_display": "Pay as you go",
                        "amount_next_payment_minor": 0,
                        "current_period_end": None,
                        "cancel_at_period_end": False,
                        "is_payg": True,
                        "service_code": "voxbulk",
                    }
            return None
        return finance

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
            "web_units_included": usage.get("web_units_included", 0),
            "web_units_used": usage.get("web_units_used", 0),
            "web_units_remaining": usage.get("web_units_remaining", 0),
            "survey_units_included": usage.get("survey_units_included", 0),
            "survey_units_used": usage.get("survey_units_used", 0),
            "survey_units_remaining": usage.get("survey_units_remaining", 0),
            "web_mode": usage.get("web_mode", "none"),
        }

    @staticmethod
    def smart_card_summary(db: Session, org_id: str) -> dict[str, Any] | None:
        org = db.get(Organisation, org_id)
        if org is None:
            return None
        sub = BillingAccessService.get_subscription(db, org_id, service_code=SMART_CARD_SERVICE_CODE)
        if sub is None:
            return None
        status = str(sub.status or "").lower()
        if status in {"cancelled", "inactive", "expired"}:
            return None
        finance = SubscriptionSummaryService._finance_for_sub(db, sub, org=org)
        if finance is None:
            return None
        return {
            **finance,
            "service_code": SMART_CARD_SERVICE_CODE,
            "seat_quantity": int(sub.seat_quantity or 0),
            "billable_seat_quantity": int(getattr(sub, "billable_seat_quantity", None) or 0)
            if getattr(sub, "billable_seat_quantity", None) is not None
            else int(sub.seat_quantity or 0),
            "free_seat_quantity": max(
                0,
                int(sub.seat_quantity or 0)
                - (
                    int(getattr(sub, "billable_seat_quantity", None) or 0)
                    if getattr(sub, "billable_seat_quantity", None) is not None
                    else int(sub.seat_quantity or 0)
                ),
            ),
            "added_seats_free_until": (
                sub.added_seats_free_until.isoformat()
                if getattr(sub, "added_seats_free_until", None)
                else None
            ),
            "trial_started_at": sub.created_at.isoformat() if getattr(sub, "created_at", None) else None,
            "trial_ends_at": (
                sub.current_period_end.isoformat()
                if status in {"trial", "trialing"} and sub.current_period_end
                else None
            ),
            "is_trial": status in {"trial", "trialing"},
        }

    @staticmethod
    def build_org_summary(db: Session, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            return {"ok": False, "core": None, "feedback": None, "smart_card": None}
        from app.services.billing_currency import resolve_org_currency

        return {
            "ok": True,
            "currency": resolve_org_currency(db, org),
            "core": SubscriptionSummaryService.core_summary(db, org_id),
            "feedback": SubscriptionSummaryService.feedback_summary(db, org_id),
            "smart_card": SubscriptionSummaryService.smart_card_summary(db, org_id),
        }
