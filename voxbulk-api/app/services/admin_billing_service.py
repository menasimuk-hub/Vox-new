from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription


@dataclass(frozen=True)
class AdminBillingOverview:
    plans_total: int
    subscriptions_total: int
    subscriptions_active: int
    subscriptions_trial: int
    subscriptions_past_due: int
    subscriptions_pending_payment: int
    subscriptions_test_mode: int
    subscriptions_production_mode: int
    latest_subscription_created_at: datetime | None


class AdminBillingService:
    @staticmethod
    def list_plans(db: Session) -> list[Plan]:
        return list(db.execute(select(Plan).order_by(Plan.price_gbp_pence.asc(), Plan.name.asc())).scalars())

    @staticmethod
    def subscriptions_overview(db: Session, *, limit_window: int = 500) -> AdminBillingOverview:
        plans_total = db.execute(select(func.count()).select_from(Plan)).scalar_one()

        ids = [
            r[0]
            for r in db.execute(select(Subscription.id).order_by(Subscription.created_at.desc()).limit(limit_window)).all()
        ]
        if not ids:
            return AdminBillingOverview(
                plans_total=int(plans_total),
                subscriptions_total=0,
                subscriptions_active=0,
                subscriptions_trial=0,
                subscriptions_past_due=0,
                subscriptions_pending_payment=0,
                subscriptions_test_mode=0,
                subscriptions_production_mode=0,
                latest_subscription_created_at=None,
            )

        counts = dict(
            db.execute(
                select(Subscription.status, func.count()).where(Subscription.id.in_(ids)).group_by(Subscription.status)
            ).all()
        )
        modes = dict(
            db.execute(
                select(Subscription.payment_mode, func.count()).where(Subscription.id.in_(ids)).group_by(Subscription.payment_mode)
            ).all()
        )
        latest = db.execute(select(func.max(Subscription.created_at)).where(Subscription.id.in_(ids))).scalar_one()
        return AdminBillingOverview(
            plans_total=int(plans_total),
            subscriptions_total=len(ids),
            subscriptions_active=int(counts.get("active", 0)),
            subscriptions_trial=int(counts.get("trial", 0)),
            subscriptions_past_due=int(counts.get("past_due", 0)),
            subscriptions_pending_payment=int(counts.get("pending_payment", 0)),
            subscriptions_test_mode=int(modes.get("test", 0)),
            subscriptions_production_mode=int(modes.get("production", 0)),
            latest_subscription_created_at=latest,
        )

    @staticmethod
    def list_subscriptions(
        db: Session,
        *,
        limit: int = 200,
        status: str | None = None,
        provider: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit or 200), 500))
        q = (
            select(Subscription, Organisation, Plan)
            .join(Organisation, Organisation.id == Subscription.org_id)
            .join(Plan, Plan.id == Subscription.plan_id)
        )
        if status:
            q = q.where(Subscription.status == str(status).strip().lower())
        if provider:
            q = q.where(Subscription.payment_provider == str(provider).strip().lower())
        if search:
            term = f"%{str(search).strip()}%"
            q = q.where(
                or_(
                    Organisation.name.ilike(term),
                    Organisation.contact_email.ilike(term),
                    Plan.name.ilike(term),
                    Plan.code.ilike(term),
                )
            )
        rows = list(db.execute(q.order_by(Subscription.updated_at.desc()).limit(cap)).all())

        pending_ids = {sub.pending_plan_id for sub, _, _ in rows if sub.pending_plan_id}
        pending_plans: dict[str, Plan] = {}
        if pending_ids:
            pending_plans = {
                p.id: p
                for p in db.execute(select(Plan).where(Plan.id.in_(pending_ids))).scalars().all()
            }

        out: list[dict[str, Any]] = []
        for sub, org, plan in rows:
            pending = pending_plans.get(sub.pending_plan_id) if sub.pending_plan_id else None
            out.append(
                {
                    "id": sub.id,
                    "org_id": sub.org_id,
                    "org_name": org.name,
                    "org_email": org.contact_email,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                    "plan_name": plan.name,
                    "plan_price_gbp_pence": plan.price_gbp_pence,
                    "pending_plan_id": sub.pending_plan_id,
                    "pending_plan_code": pending.code if pending else None,
                    "pending_plan_name": pending.name if pending else None,
                    "status": sub.status,
                    "payment_provider": sub.payment_provider,
                    "payment_mode": sub.payment_mode,
                    "external_customer_id": sub.external_customer_id,
                    "external_subscription_id": sub.external_subscription_id,
                    "current_period_end": sub.current_period_end,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at,
                }
            )
        return out

