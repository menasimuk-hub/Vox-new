"""Interview campaign launch eligibility — package allowance or PAYG wallet (125% hold)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_access_service import BillingAccessService
from app.services.interview_billing_context import org_interview_billing_context
from app.services.interview_launch_service import InterviewLaunchService
from app.services.launch_billing_service import LaunchBillingError, LaunchBillingService
from app.services.survey_billing_context import org_survey_billing_context

logger = logging.getLogger(__name__)


class InterviewLaunchEligibilityError(ValueError):
    pass


class InterviewLaunchEligibilityService:
    @staticmethod
    def _order_config(order: ServiceOrder) -> dict[str, Any]:
        try:
            data = json.loads(order.config_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _duration_minutes(config: dict[str, Any]) -> int:
        raw = (
            config.get("estimated_duration_min")
            or config.get("expected_duration_minutes")
            or config.get("duration_min")
        )
        try:
            return max(1, int(raw)) if raw else 12
        except (TypeError, ValueError):
            return 12

    @staticmethod
    def compute(db: Session, order: ServiceOrder, org: Organisation) -> dict[str, Any]:
        if order.service_code != "interview":
            raise InterviewLaunchEligibilityError("Launch eligibility is only for interview orders")

        config = InterviewLaunchEligibilityService._order_config(order)
        billing_ctx = org_interview_billing_context(db, org)
        survey_billing = org_survey_billing_context(db, org)
        recipient_count = max(0, int(order.recipient_count or 0))
        duration_min = InterviewLaunchEligibilityService._duration_minutes(config)

        base: dict[str, Any] = {
            "order_id": order.id,
            "campaign_name": order.title,
            "recipient_count": recipient_count,
            "estimated_call_minutes": duration_min * recipient_count,
            "duration_minutes": duration_min,
            "can_launch": False,
            "payment_required": True,
            "mode": "blocked",
            "launch_action": "blocked",
            "billing": {**survey_billing, **billing_ctx},
        }

        if InterviewLaunchService.org_has_package_launch_access(db, org):
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_included",
                    "launch_action": "launch",
                    "summary": f"Included in {billing_ctx.get('plan_name') or 'your package'}",
                    "amount_due_pence": 0,
                    "amount_due_display": f"Included in {billing_ctx.get('plan_name') or 'your package'}",
                }
            )
            return base

        access_block = BillingAccessService.launch_block_reason(
            db,
            org,
            payg_wallet_launch=True,
        )
        if access_block:
            base["block_reason"] = access_block
            base["block_reason_code"] = "billing_access_blocked"
            base["summary"] = access_block
            return base

        if recipient_count <= 0:
            base["block_reason"] = "Upload at least one candidate before launch."
            base["block_reason_code"] = "no_recipients"
            return base

        can_invoice = bool(survey_billing.get("can_launch_and_invoice"))
        est = LaunchBillingService.estimate_phone_launch(
            db,
            org,
            recipient_count=recipient_count,
            duration_min=duration_min,
            calls_remaining_min=int(survey_billing.get("calls_remaining") or 0),
            has_subscription=can_invoice,
        )
        method = str(est.get("payment_method") or "")
        total = int(est.get("total_minor") or 0)
        base.update(
            {
                "currency": est.get("currency"),
                "amount_due_pence": total,
                "amount_due_display": est.get("total_display"),
                "estimated_cost_minor": int(est.get("estimated_cost_minor") or total),
                "estimated_cost_display": est.get("estimated_cost_display"),
                "required_wallet_minor": int(est.get("required_wallet_minor") or 0),
                "required_wallet_display": est.get("required_wallet_display"),
                "wallet_buffer_percent": int(est.get("wallet_buffer_percent") or 100),
                "top_up_minor": int(est.get("top_up_minor") or 0),
                "wallet_balance_minor": int(est.get("wallet_balance_minor") or 0),
                "wallet_balance_display": est.get("wallet_balance_display"),
                "wallet_charge_minor": int(est.get("wallet_charge_minor") or 0),
                "wallet_shortfall_minor": int(est.get("wallet_shortfall_minor") or 0),
                "launch_billing": est,
            }
        )

        if method == "wallet":
            hold = est.get("wallet_charge_display") or est.get("total_display")
            est_cost = est.get("estimated_cost_display") or est.get("total_display")
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "wallet",
                    "launch_action": "launch",
                    "summary": (
                        f"AI interview screening: estimated {est_cost} — 125% hold ({hold}) "
                        f"debited at launch. Unused hold refunded after calls finish."
                    ),
                }
            )
        elif method == "direct_debit":
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_overage",
                    "launch_action": "launch",
                    "summary": f"Extra minutes invoiced by Direct Debit ({est.get('total_display')}).",
                }
            )
        elif method == "allowance":
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_included",
                    "launch_action": "launch",
                    "summary": "Covered by plan call minutes.",
                }
            )
        else:
            base.update(
                {
                    "mode": "wallet_insufficient",
                    "launch_action": "topup_required",
                    "block_reason": str(est.get("block_reason") or "Wallet balance is insufficient."),
                    "block_reason_code": "wallet_insufficient",
                    "summary": str(est.get("block_reason") or "Top up your wallet to launch."),
                }
            )
        return base

    @staticmethod
    def approve_if_covered(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        if order.payment_status == "approved":
            return order
        if InterviewLaunchService.org_has_package_launch_access(db, org):
            return InterviewLaunchService.approve_for_subscription_package(db, order, org)

        eligibility = InterviewLaunchEligibilityService.compute(db, order, org)
        breakdown = eligibility.get("launch_billing")
        if not eligibility.get("can_launch") or not isinstance(breakdown, dict):
            raise InterviewLaunchEligibilityError(
                str(eligibility.get("block_reason") or eligibility.get("summary") or "Payment required before launch")
            )
        try:
            LaunchBillingService.charge_launch(db, order, org, breakdown)
        except LaunchBillingError as e:
            raise InterviewLaunchEligibilityError(str(e)) from e
        db.refresh(order)
        return order
