"""Repair Customer Feedback subscriptions mis-tagged or missing usage periods."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackUsagePeriod
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.org_audit_service import OrgAuditService


class FeedbackSubscriptionRepairService:
    @staticmethod
    def _is_feedback_plan(plan: Plan | None) -> bool:
        if plan is None:
            return False
        kind = str(plan.service_kind or "").strip().lower()
        code = str(plan.code or "").strip().lower()
        return kind == FEEDBACK_SERVICE_CODE or code.startswith("cf_")

    @staticmethod
    def remove_ghost_voxbulk_subscriptions(db: Session, org_id: str) -> list[str]:
        """Remove or re-tag voxbulk rows that reference Customer Feedback plans."""
        org_id = str(org_id or "").strip()
        if not org_id:
            return []

        removed: list[str] = []
        voxbulk_sub = BillingAccessService.get_subscription(db, org_id, service_code="voxbulk")
        if voxbulk_sub is None or not voxbulk_sub.plan_id:
            return removed

        plan = db.get(Plan, voxbulk_sub.plan_id)
        if not FeedbackSubscriptionRepairService._is_feedback_plan(plan):
            return removed

        feedback_sub = BillingAccessService.get_feedback_subscription(db, org_id)
        if feedback_sub is not None and feedback_sub.id != voxbulk_sub.id:
            sub_id = voxbulk_sub.id
            db.delete(voxbulk_sub)
            OrgAuditService.record(
                db,
                org_id=org_id,
                action="Removed ghost Core subscription row",
                event_type="subscription.ghost_voxbulk_removed",
                entity_type="subscription",
                entity_id=sub_id,
                metadata={"plan_id": plan.id if plan else None, "plan_code": getattr(plan, "code", None)},
                commit=False,
            )
            db.commit()
            removed.append(sub_id)
            return removed

        if str(voxbulk_sub.service_code or "") != FEEDBACK_SERVICE_CODE:
            voxbulk_sub.service_code = FEEDBACK_SERVICE_CODE
            db.add(voxbulk_sub)
            db.commit()
        return removed

    @staticmethod
    def repair_org(db: Session, org_id: str) -> dict[str, Any]:
        org_id = str(org_id or "").strip()
        if not org_id:
            return {"ok": False, "error": "org_id required"}

        fixed: list[str] = []
        removed = FeedbackSubscriptionRepairService.remove_ghost_voxbulk_subscriptions(db, org_id)
        fixed.extend(f"removed:{sub_id}" for sub_id in removed)
        subs = list(
            db.execute(
                select(Subscription)
                .where(Subscription.org_id == org_id)
                .order_by(Subscription.updated_at.desc())
            )
            .scalars()
            .all()
        )
        for sub in subs:
            if not sub.plan_id:
                continue
            plan = db.get(Plan, sub.plan_id)
            if plan is None or str(plan.service_kind or "") != FEEDBACK_SERVICE_CODE:
                continue
            if str(sub.service_code or "") != FEEDBACK_SERVICE_CODE:
                sub.service_code = FEEDBACK_SERVICE_CODE
                db.add(sub)
                fixed.append(f"service_code:{sub.id}")
            FeedbackBillingService.on_subscription_activated(
                db, org_id=org_id, subscription=sub, plan=plan
            )
            fixed.append(f"activated:{sub.id}")

        feedback_sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if feedback_sub is None:
            return {"ok": True, "org_id": org_id, "fixed": fixed, "active": False}

        usage = (
            db.execute(
                select(FeedbackUsagePeriod)
                .where(FeedbackUsagePeriod.org_id == org_id)
                .order_by(FeedbackUsagePeriod.period_start.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        return {
            "ok": True,
            "org_id": org_id,
            "fixed": fixed,
            "active": True,
            "subscription_id": feedback_sub.id,
            "usage_period_id": usage.id if usage else None,
        }

    @staticmethod
    def repair_all(db: Session) -> dict[str, Any]:
        org_ids = set(
            db.execute(
                select(Subscription.org_id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Plan.service_kind == FEEDBACK_SERVICE_CODE)
                .distinct()
            )
            .scalars()
            .all()
        )
        results = [FeedbackSubscriptionRepairService.repair_org(db, org_id) for org_id in sorted(org_ids)]
        return {"ok": True, "count": len(results), "results": results}
